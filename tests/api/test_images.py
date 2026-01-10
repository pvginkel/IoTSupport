"""Tests for image proxy API endpoints."""

import io
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
from flask import Flask
from PIL import Image


class TestImagesApi:
    """Test cases for /api/images endpoints."""

    def _create_test_image(self, width: int, height: int) -> bytes:
        """Create a test PNG image in memory.

        Args:
            width: Image width in pixels
            height: Image height in pixels

        Returns:
            PNG image data as bytes
        """
        img = Image.new("RGBA", (width, height), color=(0, 0, 255, 255))
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        return buffer.getvalue()

    def test_get_lvgl_image_success(self, app: Flask, client: Any):
        """Test successful image fetch and conversion."""
        test_image_data = self._create_test_image(100, 100)
        mock_response = MagicMock()
        mock_response.content = test_image_data
        mock_response.status_code = 200

        with patch("httpx.Client") as mock_client:
            mock_client_instance = MagicMock()
            mock_client_instance.get.return_value = mock_response
            mock_client.return_value.__enter__.return_value = mock_client_instance

            response = client.get(
                "/api/images/lvgl?url=https://example.com/image.png"
            )

            assert response.status_code == 200
            assert response.content_type == "application/octet-stream"
            assert response.headers["Cache-Control"] == "no-store"
            assert len(response.data) > 0
            # LVGL binary format starts with magic number
            assert response.data[0] == 0x19

    def test_get_lvgl_image_missing_url(self, app: Flask, client: Any):
        """Test request without required url parameter."""
        response = client.get("/api/images/lvgl")

        assert response.status_code == 400
        json_data = response.get_json()
        # Validation errors return a list of error dicts
        assert isinstance(json_data, list) and len(json_data) > 0

    def test_get_lvgl_image_invalid_url(self, app: Flask, client: Any):
        """Test request with invalid URL format."""
        response = client.get("/api/images/lvgl?url=not-a-valid-url")

        assert response.status_code == 400
        json_data = response.get_json()
        # Validation errors return a list of error dicts
        assert isinstance(json_data, list) and len(json_data) > 0

    def test_get_lvgl_image_with_headers(self, app: Flask, client: Any):
        """Test image fetch with forwarded headers."""
        test_image_data = self._create_test_image(50, 50)
        mock_response = MagicMock()
        mock_response.content = test_image_data
        mock_response.status_code = 200

        with patch("httpx.Client") as mock_client:
            mock_client_instance = MagicMock()
            mock_client_instance.get.return_value = mock_response
            mock_client.return_value.__enter__.return_value = mock_client_instance

            response = client.get(
                "/api/images/lvgl?url=https://example.com/secure.png&headers=Authorization",
                headers={"Authorization": "Bearer token123"},
            )

            assert response.status_code == 200
            assert response.data[0] == 0x19

            # Verify headers were forwarded
            call_args = mock_client_instance.get.call_args
            assert "Authorization" in call_args[1]["headers"]
            assert call_args[1]["headers"]["Authorization"] == "Bearer token123"

    def test_get_lvgl_image_missing_required_header(self, app: Flask, client: Any):
        """Test request with headers parameter but missing header in request."""
        response = client.get(
            "/api/images/lvgl?url=https://example.com/secure.png&headers=Authorization"
        )

        assert response.status_code == 400
        json_data = response.get_json()
        assert "error" in json_data
        assert "Authorization" in json_data["error"]

    def test_get_lvgl_image_with_resize(self, app: Flask, client: Any):
        """Test image fetch with resize parameters."""
        test_image_data = self._create_test_image(200, 200)
        mock_response = MagicMock()
        mock_response.content = test_image_data
        mock_response.status_code = 200

        with patch("httpx.Client") as mock_client:
            mock_client_instance = MagicMock()
            mock_client_instance.get.return_value = mock_response
            mock_client.return_value.__enter__.return_value = mock_client_instance

            response = client.get(
                "/api/images/lvgl?url=https://example.com/large.png&width=100&height=100"
            )

            assert response.status_code == 200
            assert len(response.data) > 0

    def test_get_lvgl_image_invalid_width(self, app: Flask, client: Any):
        """Test request with invalid width parameter."""
        response = client.get(
            "/api/images/lvgl?url=https://example.com/image.png&width=-10"
        )

        assert response.status_code == 400
        json_data = response.get_json()
        # Validation errors return a list of error dicts
        assert isinstance(json_data, list) and len(json_data) > 0

    def test_get_lvgl_image_invalid_height(self, app: Flask, client: Any):
        """Test request with invalid height parameter."""
        response = client.get(
            "/api/images/lvgl?url=https://example.com/image.png&height=0"
        )

        assert response.status_code == 400
        json_data = response.get_json()
        # Validation errors return a list of error dicts
        assert isinstance(json_data, list) and len(json_data) > 0

    def test_get_lvgl_image_external_timeout(self, app: Flask, client: Any):
        """Test handling of external URL timeout."""
        with patch("httpx.Client") as mock_client:
            mock_client_instance = MagicMock()
            mock_client_instance.get.side_effect = httpx.TimeoutException(
                "Request timeout"
            )
            mock_client.return_value.__enter__.return_value = mock_client_instance

            response = client.get(
                "/api/images/lvgl?url=https://slow.example.com/image.png"
            )

            assert response.status_code == 502
            json_data = response.get_json()
            assert "error" in json_data
            assert "EXTERNAL_SERVICE_ERROR" in json_data.get("code", "")

    def test_get_lvgl_image_external_404(self, app: Flask, client: Any):
        """Test handling of HTTP 404 from external URL."""
        mock_response = MagicMock()
        mock_response.status_code = 404

        with patch("httpx.Client") as mock_client:
            mock_client_instance = MagicMock()
            mock_client_instance.get.side_effect = httpx.HTTPStatusError(
                "Not found", request=MagicMock(), response=mock_response
            )
            mock_client.return_value.__enter__.return_value = mock_client_instance

            response = client.get(
                "/api/images/lvgl?url=https://example.com/missing.png"
            )

            assert response.status_code == 502
            json_data = response.get_json()
            assert "error" in json_data

    def test_get_lvgl_image_network_error(self, app: Flask, client: Any):
        """Test handling of network error."""
        with patch("httpx.Client") as mock_client:
            mock_client_instance = MagicMock()
            mock_client_instance.get.side_effect = httpx.RequestError(
                "Connection failed"
            )
            mock_client.return_value.__enter__.return_value = mock_client_instance

            response = client.get(
                "/api/images/lvgl?url=https://unreachable.local/image.png"
            )

            assert response.status_code == 502
            json_data = response.get_json()
            assert "error" in json_data

    def test_get_lvgl_image_invalid_image_data(self, app: Flask, client: Any):
        """Test handling of non-image response data."""
        mock_response = MagicMock()
        mock_response.content = b"<html><body>Not an image</body></html>"
        mock_response.status_code = 200

        with patch("httpx.Client") as mock_client:
            mock_client_instance = MagicMock()
            mock_client_instance.get.return_value = mock_response
            mock_client.return_value.__enter__.return_value = mock_client_instance

            response = client.get(
                "/api/images/lvgl?url=https://example.com/notimage.png"
            )

            assert response.status_code == 500
            json_data = response.get_json()
            assert "error" in json_data
            assert "PROCESSING_ERROR" in json_data.get("code", "")

    def test_get_lvgl_image_multiple_headers(self, app: Flask, client: Any):
        """Test forwarding multiple headers."""
        test_image_data = self._create_test_image(50, 50)
        mock_response = MagicMock()
        mock_response.content = test_image_data
        mock_response.status_code = 200

        with patch("httpx.Client") as mock_client:
            mock_client_instance = MagicMock()
            mock_client_instance.get.return_value = mock_response
            mock_client.return_value.__enter__.return_value = mock_client_instance

            response = client.get(
                "/api/images/lvgl?url=https://example.com/secure.png&headers=Authorization,X-API-Key",
                headers={
                    "Authorization": "Bearer token123",
                    "X-API-Key": "secret-key",
                },
            )

            assert response.status_code == 200

            # Verify both headers were forwarded
            call_args = mock_client_instance.get.call_args
            headers = call_args[1]["headers"]
            assert "Authorization" in headers
            assert "X-API-Key" in headers
            assert headers["Authorization"] == "Bearer token123"
            assert headers["X-API-Key"] == "secret-key"

    def test_get_lvgl_image_width_only(self, app: Flask, client: Any):
        """Test image resize with width only."""
        test_image_data = self._create_test_image(200, 100)
        mock_response = MagicMock()
        mock_response.content = test_image_data
        mock_response.status_code = 200

        with patch("httpx.Client") as mock_client:
            mock_client_instance = MagicMock()
            mock_client_instance.get.return_value = mock_response
            mock_client.return_value.__enter__.return_value = mock_client_instance

            response = client.get(
                "/api/images/lvgl?url=https://example.com/wide.png&width=100"
            )

            assert response.status_code == 200
            assert len(response.data) > 0

    def test_get_lvgl_image_height_only(self, app: Flask, client: Any):
        """Test image resize with height only."""
        test_image_data = self._create_test_image(100, 200)
        mock_response = MagicMock()
        mock_response.content = test_image_data
        mock_response.status_code = 200

        with patch("httpx.Client") as mock_client:
            mock_client_instance = MagicMock()
            mock_client_instance.get.return_value = mock_response
            mock_client.return_value.__enter__.return_value = mock_client_instance

            response = client.get(
                "/api/images/lvgl?url=https://example.com/tall.png&height=100"
            )

            assert response.status_code == 200
            assert len(response.data) > 0

    def test_get_lvgl_image_cache_control_header(self, app: Flask, client: Any):
        """Test that Cache-Control: no-store header is set."""
        test_image_data = self._create_test_image(50, 50)
        mock_response = MagicMock()
        mock_response.content = test_image_data
        mock_response.status_code = 200

        with patch("httpx.Client") as mock_client:
            mock_client_instance = MagicMock()
            mock_client_instance.get.return_value = mock_response
            mock_client.return_value.__enter__.return_value = mock_client_instance

            response = client.get(
                "/api/images/lvgl?url=https://example.com/image.png"
            )

            assert response.status_code == 200
            assert "Cache-Control" in response.headers
            assert response.headers["Cache-Control"] == "no-store"
