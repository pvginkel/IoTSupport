"""Tests for CasImageService thumbnail generation from CAS originals."""

import hashlib
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from PIL import Image

from app.app_config import AppSettings
from app.exceptions import InvalidOperationException
from app.services.container import ServiceContainer


class TestCasImageService:
    """Tests for CasImageService thumbnail caching."""

    def test_construction_creates_thumbnail_directory(
        self, container: ServiceContainer, test_app_settings: AppSettings
    ) -> None:
        """Constructing the service creates thumbnail_storage_path."""
        thumbnail_dir = test_app_settings.thumbnail_storage_path
        assert not thumbnail_dir.exists()

        container.cas_image_service()

        assert thumbnail_dir.is_dir()

    def test_get_thumbnail_for_hash_generates_jpeg(
        self, container: ServiceContainer, test_app_settings: AppSettings, make_cas_image: Any
    ) -> None:
        """A thumbnail is rendered from the S3 original into the cache dir."""
        content_hash = make_cas_image(400, 200)
        service = container.cas_image_service()

        thumbnail_path = service.get_thumbnail_for_hash(content_hash, 100)

        assert Path(thumbnail_path) == test_app_settings.thumbnail_storage_path / f"{content_hash}_100.jpg"
        with Image.open(thumbnail_path) as thumbnail:
            assert thumbnail.format == "JPEG"
            # Fits in 100x100 and keeps the original's 2:1 aspect ratio
            assert thumbnail.size == (100, 50)
            # Pixels come from the original; JPEG is lossy, so allow some drift
            pixel = thumbnail.convert("RGB").getpixel((50, 25))
            assert isinstance(pixel, tuple)
            assert all(abs(actual - expected) <= 10 for actual, expected in zip(pixel, (200, 30, 60), strict=True))

    def test_get_thumbnail_for_hash_serves_cached_file(
        self, container: ServiceContainer, make_cas_image: Any
    ) -> None:
        """A second call returns the cached thumbnail without reading S3."""
        content_hash = make_cas_image(300, 300)
        service = container.cas_image_service()
        first_path = service.get_thumbnail_for_hash(content_hash, 64)

        with patch.object(service.s3_service, "download_file") as download_file:
            second_path = service.get_thumbnail_for_hash(content_hash, 64)

        assert second_path == first_path
        download_file.assert_not_called()

    def test_get_thumbnail_for_hash_failed_s3_read(
        self, container: ServiceContainer, test_app_settings: AppSettings
    ) -> None:
        """A failing S3 read raises InvalidOperationException and caches nothing."""
        missing_hash = hashlib.sha256(uuid.uuid4().bytes).hexdigest()
        service = container.cas_image_service()

        with pytest.raises(InvalidOperationException):
            service.get_thumbnail_for_hash(missing_hash, 64)

        assert not (test_app_settings.thumbnail_storage_path / f"{missing_hash}_64.jpg").exists()
