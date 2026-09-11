"""Tests for the CAS content endpoint."""

import io
import uuid
from typing import Any

import pytest
from flask.testing import FlaskClient
from PIL import Image

from app.services.container import ServiceContainer

IMMUTABLE_CACHE_CONTROL = "public, max-age=31536000, immutable"


class TestCasApi:
    """Test cases for GET /api/cas/<hash>.

    The endpoint injects CasImageService on every request, thumbnail or not,
    and the service reads thumbnail_storage_path when constructed.
    """

    def test_get_content_serves_original(self, client: FlaskClient, container: ServiceContainer) -> None:
        """The stored blob is served with an immutable cache header."""
        s3_service = container.s3_service()
        content = uuid.uuid4().bytes
        s3_service.upload_file(io.BytesIO(content), s3_service.generate_cas_key(content))

        response = client.get(f"/api/cas/{s3_service.compute_hash(content)}")

        assert response.status_code == 200
        assert response.data == content
        assert response.content_type == "application/octet-stream"
        assert response.headers["Cache-Control"] == IMMUTABLE_CACHE_CONTROL

    def test_get_thumbnail_serves_jpeg(self, client: FlaskClient, make_cas_image: Any) -> None:
        """?thumbnail=N serves a JPEG no larger than N x N."""
        content_hash = make_cas_image(400, 200)

        response = client.get(f"/api/cas/{content_hash}?thumbnail=100")

        assert response.status_code == 200
        assert response.content_type == "image/jpeg"
        assert response.headers["Cache-Control"] == IMMUTABLE_CACHE_CONTROL
        with Image.open(io.BytesIO(response.data)) as thumbnail:
            assert thumbnail.format == "JPEG"
            assert thumbnail.size == (100, 50)

    @pytest.mark.parametrize("size", [0, 1001])
    def test_get_thumbnail_rejects_out_of_range_size(self, client: FlaskClient, size: int) -> None:
        """Thumbnail sizes outside 1..1000 are rejected."""
        response = client.get(f"/api/cas/{'0' * 64}?thumbnail={size}")

        assert response.status_code == 400
