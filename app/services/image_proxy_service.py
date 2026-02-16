"""Service for proxying and converting images to LVGL format."""

import io
import logging
import tempfile
import time
from pathlib import Path

import httpx
from PIL import Image
from prometheus_client import Counter, Histogram

from app.exceptions import ExternalServiceException, ProcessingException
from app.utils.lvgl import ColorFormat, CompressMethod, LVGLImage

logger = logging.getLogger(__name__)

# Image proxy Prometheus metrics (module-level)
IMAGE_PROXY_OPERATIONS_TOTAL = Counter(
    "iot_image_proxy_operations_total",
    "Total image proxy operations",
    ["status", "error_type"],
)
IMAGE_PROXY_OPERATION_DURATION = Histogram(
    "iot_image_proxy_operation_duration_seconds",
    "Duration of image proxy operations in seconds",
)
IMAGE_PROXY_FETCH_DURATION = Histogram(
    "iot_image_proxy_external_fetch_duration_seconds",
    "Duration of external image fetches in seconds",
)
IMAGE_PROXY_IMAGE_SIZE = Histogram(
    "iot_image_proxy_image_size_bytes",
    "Size of fetched images in bytes",
)


def record_image_proxy_operation(
    status: str | None,
    error_type: str | None,
    operation_duration: float | None = None,
    fetch_duration: float | None = None,
    image_size: int | None = None,
) -> None:
    """Record an image proxy operation metric."""
    try:
        if status is not None and error_type is not None:
            IMAGE_PROXY_OPERATIONS_TOTAL.labels(
                status=status, error_type=error_type
            ).inc()
        if operation_duration is not None:
            IMAGE_PROXY_OPERATION_DURATION.observe(operation_duration)
        if fetch_duration is not None:
            IMAGE_PROXY_FETCH_DURATION.observe(fetch_duration)
        if image_size is not None:
            IMAGE_PROXY_IMAGE_SIZE.observe(image_size)
    except Exception as e:
        logger.error("Error recording image proxy metric: %s", e)


class ImageProxyService:
    """Service for fetching, resizing, and converting images to LVGL format.

    This service handles:
    - Fetching images from external URLs with forwarded headers
    - Resizing images while maintaining aspect ratio (downscale only)
    - Converting images to LVGL binary format (ARGB8888)
    """

    def __init__(self) -> None:
        """Initialize the image proxy service."""

    def fetch_and_convert_image(
        self,
        url: str,
        headers: dict[str, str],
        width: int | None = None,
        height: int | None = None,
    ) -> bytes:
        """Fetch an image from a URL and convert to LVGL binary format.

        Args:
            url: URL to fetch image from
            headers: HTTP headers to forward to external URL
            width: Target width for resizing (optional, downscale only)
            height: Target height for resizing (optional, downscale only)

        Returns:
            LVGL binary image data (ARGB8888 format)

        Raises:
            ExternalServiceException: External URL fetch failed
            ProcessingException: Image processing or conversion failed
        """
        # Fetch image from external URL
        fetch_start = time.perf_counter()
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.get(url, headers=headers, follow_redirects=True)
                response.raise_for_status()
                image_data = response.content
        except httpx.TimeoutException as e:
            logger.error("External URL fetch timeout: %s", e)
            raise ExternalServiceException(
                "fetch image", "request timeout after 30 seconds"
            ) from e
        except httpx.HTTPStatusError as e:
            logger.error("External URL returned HTTP error: %s", e)
            raise ExternalServiceException(
                "fetch image", f"HTTP {e.response.status_code}"
            ) from e
        except httpx.RequestError as e:
            logger.error("External URL request failed: %s", e)
            raise ExternalServiceException(
                "fetch image", f"network error: {str(e)}"
            ) from e

        fetch_duration = time.perf_counter() - fetch_start
        image_size = len(image_data)

        logger.info(
            "Fetched image from %s (size: %d bytes, duration: %.3fs)",
            url,
            image_size,
            fetch_duration,
        )

        # Record granular fetch metrics only (operation counter recorded by API layer)
        record_image_proxy_operation(
            status=None,  # Skip counter, only record histograms
            error_type=None,
            fetch_duration=fetch_duration,
            image_size=image_size,
        )

        # Decode image with Pillow
        try:
            pil_image: Image.Image = Image.open(io.BytesIO(image_data))
            # Convert to RGBA for consistent processing
            if pil_image.mode != "RGBA":
                pil_image = pil_image.convert("RGBA")
        except Exception as e:
            logger.error("Image decode failed: %s", e)
            raise ProcessingException(
                "decode image", "invalid or corrupt image data"
            ) from e

        # Resize if dimensions provided (downscale only)
        if width is not None or height is not None:
            pil_image = self._resize_image(pil_image, width, height)

        # Convert to LVGL binary format
        try:
            lvgl_data = self._convert_to_lvgl(pil_image)
        except Exception as e:
            logger.error("LVGL conversion failed: %s", e)
            raise ProcessingException("convert to LVGL format", str(e)) from e

        logger.info(
            "LVGL conversion successful (input: %dx%d, output size: %d bytes)",
            pil_image.width,
            pil_image.height,
            len(lvgl_data),
        )

        return lvgl_data

    def _resize_image(
        self, image: Image.Image, width: int | None, height: int | None
    ) -> Image.Image:
        """Resize image while maintaining aspect ratio (downscale only).

        Args:
            image: PIL Image to resize
            width: Target width (optional)
            height: Target height (optional)

        Returns:
            Resized PIL Image (or original if no resize needed)
        """
        original_width, original_height = image.size

        # Calculate target dimensions while preserving aspect ratio
        if width is not None and height is not None:
            # Both dimensions provided - fit within bounding box
            aspect_ratio = original_width / original_height
            if aspect_ratio > 1:
                # Wider than tall - width is limiting factor
                target_width = min(width, original_width)
                target_height = int(target_width / aspect_ratio)
                if target_height > height:
                    # Height exceeds limit - height is limiting factor
                    target_height = min(height, original_height)
                    target_width = int(target_height * aspect_ratio)
            else:
                # Taller than wide - height is limiting factor
                target_height = min(height, original_height)
                target_width = int(target_height * aspect_ratio)
                if target_width > width:
                    # Width exceeds limit - width is limiting factor
                    target_width = min(width, original_width)
                    target_height = int(target_width / aspect_ratio)
        elif width is not None:
            # Only width provided
            target_width = min(width, original_width)
            aspect_ratio = original_width / original_height
            target_height = int(target_width / aspect_ratio)
        elif height is not None:
            # Only height provided
            target_height = min(height, original_height)
            aspect_ratio = original_width / original_height
            target_width = int(target_height * aspect_ratio)
        else:
            # No resize needed
            return image

        # Only resize if we're actually downscaling
        if target_width >= original_width and target_height >= original_height:
            logger.info(
                "No resize needed (original %dx%d, target %dx%d)",
                original_width,
                original_height,
                target_width,
                target_height,
            )
            return image

        logger.info(
            "Resizing image from %dx%d to %dx%d",
            original_width,
            original_height,
            target_width,
            target_height,
        )

        try:
            return image.resize(
                (target_width, target_height), resample=Image.Resampling.LANCZOS
            )
        except Exception as e:
            logger.error("Image resize failed: %s", e)
            raise ProcessingException("resize image", str(e)) from e

    def _convert_to_lvgl(self, image: Image.Image) -> bytes:
        """Convert PIL Image to LVGL binary format.

        Args:
            image: PIL Image in RGBA format

        Returns:
            LVGL binary data (ARGB8888 format)
        """
        # Create a temporary file for LVGL conversion
        # LVGLImage.to_bin() requires a filename, not in-memory conversion
        with tempfile.NamedTemporaryFile(
            suffix=".png", delete=False
        ) as temp_png, tempfile.NamedTemporaryFile(
            suffix=".bin", delete=False
        ) as temp_bin:
            temp_png_path = Path(temp_png.name)
            temp_bin_path = Path(temp_bin.name)

        try:
            # Save PIL image as PNG
            image.save(temp_png_path, format="PNG")

            # Convert PNG to LVGL binary format using upstream LVGLImage module
            lvgl_image = LVGLImage()
            lvgl_image.from_png(str(temp_png_path), cf=ColorFormat.ARGB8888)
            lvgl_image.to_bin(str(temp_bin_path), compress=CompressMethod.NONE)

            # Read binary data
            with open(temp_bin_path, "rb") as f:
                lvgl_data = f.read()

            return lvgl_data

        finally:
            # Clean up temporary files (handle each separately to avoid leaving orphans)
            try:
                temp_png_path.unlink(missing_ok=True)
            except Exception as e:
                logger.warning("Failed to clean up temp PNG file: %s", e)

            try:
                temp_bin_path.unlink(missing_ok=True)
            except Exception as e:
                logger.warning("Failed to clean up temp BIN file: %s", e)
