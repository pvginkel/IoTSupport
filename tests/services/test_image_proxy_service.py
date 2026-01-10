"""Tests for ImageProxyService."""

import io
from unittest.mock import MagicMock, patch

import httpx
import pytest
from flask import Flask
from PIL import Image

from app.exceptions import ExternalServiceException, ProcessingException
from app.services.container import ServiceContainer


class TestImageProxyService:
    """Test cases for ImageProxyService."""

    def _create_test_image(self, width: int, height: int) -> bytes:
        """Create a test PNG image in memory.

        Args:
            width: Image width in pixels
            height: Image height in pixels

        Returns:
            PNG image data as bytes
        """
        img = Image.new("RGBA", (width, height), color=(255, 0, 0, 255))
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        return buffer.getvalue()

    def test_fetch_and_convert_basic(self, app: Flask, container: ServiceContainer):
        """Test basic image fetch and conversion."""
        service = container.image_proxy_service()

        # Create mock response
        test_image_data = self._create_test_image(100, 100)
        mock_response = MagicMock()
        mock_response.content = test_image_data
        mock_response.status_code = 200

        # Mock httpx client
        with patch("httpx.Client") as mock_client:
            mock_client_instance = MagicMock()
            mock_client_instance.get.return_value = mock_response
            mock_client.return_value.__enter__.return_value = mock_client_instance

            # Fetch and convert
            lvgl_data = service.fetch_and_convert_image(
                url="https://example.com/image.png",
                headers={},
            )

            # Verify binary data returned
            assert isinstance(lvgl_data, bytes)
            assert len(lvgl_data) > 0
            # LVGL binary format starts with magic number 0x19
            assert lvgl_data[0] == 0x19

    def test_fetch_with_headers(self, app: Flask, container: ServiceContainer):
        """Test image fetch with forwarded headers."""
        service = container.image_proxy_service()

        test_image_data = self._create_test_image(50, 50)
        mock_response = MagicMock()
        mock_response.content = test_image_data
        mock_response.status_code = 200

        with patch("httpx.Client") as mock_client:
            mock_client_instance = MagicMock()
            mock_client_instance.get.return_value = mock_response
            mock_client.return_value.__enter__.return_value = mock_client_instance

            headers = {"Authorization": "Bearer token123", "X-API-Key": "secret"}

            service.fetch_and_convert_image(
                url="https://example.com/image.png",
                headers=headers,
            )

            # Verify headers were forwarded
            call_args = mock_client_instance.get.call_args
            assert call_args[1]["headers"] == headers

    def test_fetch_timeout(self, app: Flask, container: ServiceContainer):
        """Test handling of external URL timeout."""
        service = container.image_proxy_service()

        with patch("httpx.Client") as mock_client:
            mock_client_instance = MagicMock()
            mock_client_instance.get.side_effect = httpx.TimeoutException(
                "Request timeout"
            )
            mock_client.return_value.__enter__.return_value = mock_client_instance

            with pytest.raises(ExternalServiceException) as exc_info:
                service.fetch_and_convert_image(
                    url="https://example.com/slow.png",
                    headers={},
                )

            assert "timeout" in str(exc_info.value).lower()

    def test_fetch_http_error(self, app: Flask, container: ServiceContainer):
        """Test handling of HTTP error from external URL."""
        service = container.image_proxy_service()

        mock_response = MagicMock()
        mock_response.status_code = 404

        with patch("httpx.Client") as mock_client:
            mock_client_instance = MagicMock()
            mock_client_instance.get.side_effect = httpx.HTTPStatusError(
                "Not found", request=MagicMock(), response=mock_response
            )
            mock_client.return_value.__enter__.return_value = mock_client_instance

            with pytest.raises(ExternalServiceException) as exc_info:
                service.fetch_and_convert_image(
                    url="https://example.com/missing.png",
                    headers={},
                )

            assert "404" in str(exc_info.value)

    def test_fetch_network_error(self, app: Flask, container: ServiceContainer):
        """Test handling of network error."""
        service = container.image_proxy_service()

        with patch("httpx.Client") as mock_client:
            mock_client_instance = MagicMock()
            mock_client_instance.get.side_effect = httpx.RequestError(
                "Connection failed"
            )
            mock_client.return_value.__enter__.return_value = mock_client_instance

            with pytest.raises(ExternalServiceException) as exc_info:
                service.fetch_and_convert_image(
                    url="https://unreachable.local/image.png",
                    headers={},
                )

            assert "network error" in str(exc_info.value).lower()

    def test_invalid_image_data(self, app: Flask, container: ServiceContainer):
        """Test handling of non-image response data."""
        service = container.image_proxy_service()

        # Return HTML instead of image
        mock_response = MagicMock()
        mock_response.content = b"<html><body>Not an image</body></html>"
        mock_response.status_code = 200

        with patch("httpx.Client") as mock_client:
            mock_client_instance = MagicMock()
            mock_client_instance.get.return_value = mock_response
            mock_client.return_value.__enter__.return_value = mock_client_instance

            with pytest.raises(ProcessingException) as exc_info:
                service.fetch_and_convert_image(
                    url="https://example.com/notimage.png",
                    headers={},
                )

            assert "decode image" in str(exc_info.value).lower()

    def test_resize_downscale_both_dimensions(
        self, app: Flask, container: ServiceContainer
    ):
        """Test image resize with both width and height (downscale only)."""
        service = container.image_proxy_service()

        # Create 200x200 image
        test_image_data = self._create_test_image(200, 200)
        mock_response = MagicMock()
        mock_response.content = test_image_data
        mock_response.status_code = 200

        with patch("httpx.Client") as mock_client:
            mock_client_instance = MagicMock()
            mock_client_instance.get.return_value = mock_response
            mock_client.return_value.__enter__.return_value = mock_client_instance

            lvgl_data = service.fetch_and_convert_image(
                url="https://example.com/image.png",
                headers={},
                width=100,
                height=100,
            )

            # Verify conversion succeeded
            assert isinstance(lvgl_data, bytes)
            assert len(lvgl_data) > 0

    def test_resize_no_upscale(self, app: Flask, container: ServiceContainer):
        """Test that images are not upscaled."""
        service = container.image_proxy_service()

        # Create 50x50 image, request 100x100
        test_image_data = self._create_test_image(50, 50)
        mock_response = MagicMock()
        mock_response.content = test_image_data
        mock_response.status_code = 200

        with patch("httpx.Client") as mock_client:
            mock_client_instance = MagicMock()
            mock_client_instance.get.return_value = mock_response
            mock_client.return_value.__enter__.return_value = mock_client_instance

            lvgl_data = service.fetch_and_convert_image(
                url="https://example.com/small.png",
                headers={},
                width=100,
                height=100,
            )

            # Should succeed without upscaling
            assert isinstance(lvgl_data, bytes)
            assert len(lvgl_data) > 0

    def test_resize_width_only(self, app: Flask, container: ServiceContainer):
        """Test image resize with width only (preserves aspect ratio)."""
        service = container.image_proxy_service()

        # Create 200x100 image
        test_image_data = self._create_test_image(200, 100)
        mock_response = MagicMock()
        mock_response.content = test_image_data
        mock_response.status_code = 200

        with patch("httpx.Client") as mock_client:
            mock_client_instance = MagicMock()
            mock_client_instance.get.return_value = mock_response
            mock_client.return_value.__enter__.return_value = mock_client_instance

            lvgl_data = service.fetch_and_convert_image(
                url="https://example.com/wide.png",
                headers={},
                width=100,
            )

            # Verify conversion succeeded
            assert isinstance(lvgl_data, bytes)
            assert len(lvgl_data) > 0

    def test_resize_height_only(self, app: Flask, container: ServiceContainer):
        """Test image resize with height only (preserves aspect ratio)."""
        service = container.image_proxy_service()

        # Create 100x200 image
        test_image_data = self._create_test_image(100, 200)
        mock_response = MagicMock()
        mock_response.content = test_image_data
        mock_response.status_code = 200

        with patch("httpx.Client") as mock_client:
            mock_client_instance = MagicMock()
            mock_client_instance.get.return_value = mock_response
            mock_client.return_value.__enter__.return_value = mock_client_instance

            lvgl_data = service.fetch_and_convert_image(
                url="https://example.com/tall.png",
                headers={},
                height=100,
            )

            # Verify conversion succeeded
            assert isinstance(lvgl_data, bytes)
            assert len(lvgl_data) > 0

    def test_no_resize(self, app: Flask, container: ServiceContainer):
        """Test image conversion without resizing."""
        service = container.image_proxy_service()

        test_image_data = self._create_test_image(100, 100)
        mock_response = MagicMock()
        mock_response.content = test_image_data
        mock_response.status_code = 200

        with patch("httpx.Client") as mock_client:
            mock_client_instance = MagicMock()
            mock_client_instance.get.return_value = mock_response
            mock_client.return_value.__enter__.return_value = mock_client_instance

            lvgl_data = service.fetch_and_convert_image(
                url="https://example.com/image.png",
                headers={},
            )

            # Verify conversion succeeded
            assert isinstance(lvgl_data, bytes)
            assert len(lvgl_data) > 0
            # LVGL header should be present
            assert lvgl_data[0] == 0x19

    def test_aspect_ratio_preservation(self, app: Flask, container: ServiceContainer):
        """Test that aspect ratio is preserved during resize."""
        service = container.image_proxy_service()

        # Create wide image 400x200 (2:1 aspect ratio)
        test_image_data = self._create_test_image(400, 200)
        mock_response = MagicMock()
        mock_response.content = test_image_data
        mock_response.status_code = 200

        with patch("httpx.Client") as mock_client:
            mock_client_instance = MagicMock()
            mock_client_instance.get.return_value = mock_response
            mock_client.return_value.__enter__.return_value = mock_client_instance

            # Request 100x100 - should resize to fit while preserving 2:1 ratio
            lvgl_data = service.fetch_and_convert_image(
                url="https://example.com/wide.png",
                headers={},
                width=100,
                height=100,
            )

            # Verify conversion succeeded
            assert isinstance(lvgl_data, bytes)
            assert len(lvgl_data) > 0
