"""Firmware management service for device models."""

import logging
import os
import struct
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from app.exceptions import RecordNotFoundException, ValidationException

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# ESP32 AppInfo structure constants
# The AppInfo structure is located at offset 32 in the firmware binary
# (24-byte image header + 8-byte segment header)
APP_INFO_OFFSET = 32

# Magic number 0xABCD5432 (little-endian) identifies valid AppInfo
APP_INFO_MAGIC = 0xABCD5432

# Version string is at offset 16 within the AppInfo structure
# (32 bytes total: offset 48-79 in the binary)
VERSION_OFFSET_IN_APPINFO = 16
VERSION_MAX_LENGTH = 32

# Minimum file size to contain valid AppInfo header
MIN_FIRMWARE_SIZE = APP_INFO_OFFSET + VERSION_OFFSET_IN_APPINFO + VERSION_MAX_LENGTH


class FirmwareService:
    """Service for managing firmware files for device models.

    Handles firmware upload, download, and version extraction from ESP32 binaries.
    Firmware files are stored on the filesystem at ASSETS_DIR/firmware-<model_code>.bin
    """

    def __init__(self, assets_dir: Path) -> None:
        """Initialize firmware service.

        Args:
            assets_dir: Directory for storing firmware files
        """
        self.assets_dir = assets_dir
        logger.info("FirmwareService initialized with assets_dir: %s", assets_dir)

    def get_firmware_path(self, model_code: str) -> Path:
        """Get the filesystem path for a model's firmware.

        Args:
            model_code: The device model code

        Returns:
            Path to the firmware file
        """
        return self.assets_dir / f"firmware-{model_code}.bin"

    def firmware_exists(self, model_code: str) -> bool:
        """Check if firmware exists for a model.

        Args:
            model_code: The device model code

        Returns:
            True if firmware file exists
        """
        return self.get_firmware_path(model_code).exists()

    def get_firmware(self, model_code: str) -> bytes:
        """Get firmware binary content for a model.

        Args:
            model_code: The device model code

        Returns:
            Firmware binary content

        Raises:
            RecordNotFoundException: If firmware doesn't exist
        """
        path = self.get_firmware_path(model_code)
        if not path.exists():
            raise RecordNotFoundException("Firmware", model_code)

        return path.read_bytes()

    def save_firmware(self, model_code: str, content: bytes) -> str:
        """Save firmware binary and extract version.

        Uses atomic write with temp file to prevent partial writes.

        Args:
            model_code: The device model code
            content: Firmware binary content

        Returns:
            Extracted firmware version string

        Raises:
            ValidationException: If firmware format is invalid
        """
        # Validate and extract version before saving
        version = self.extract_version(content)

        # Save firmware atomically
        target_path = self.get_firmware_path(model_code)

        # Write to temp file first, then rename atomically
        fd, temp_path = tempfile.mkstemp(
            dir=self.assets_dir, suffix=".tmp"
        )
        try:
            os.write(fd, content)
            os.close(fd)
            os.replace(temp_path, target_path)
            logger.info("Saved firmware for model %s, version %s", model_code, version)
        except Exception:
            # Clean up temp file on failure
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            raise

        return version

    def delete_firmware(self, model_code: str) -> None:
        """Delete firmware file for a model.

        Best-effort deletion - logs errors but doesn't raise.

        Args:
            model_code: The device model code
        """
        path = self.get_firmware_path(model_code)
        if path.exists():
            try:
                path.unlink()
                logger.info("Deleted firmware for model %s", model_code)
            except OSError as e:
                logger.warning("Failed to delete firmware for %s: %s", model_code, e)

    def extract_version(self, content: bytes) -> str:
        """Extract firmware version from ESP32 binary.

        Parses the ESP-IDF AppInfo structure to extract the version string.

        Args:
            content: Firmware binary content

        Returns:
            Version string

        Raises:
            ValidationException: If firmware format is invalid
        """
        # Check minimum size
        if len(content) < MIN_FIRMWARE_SIZE:
            raise ValidationException(
                f"Invalid firmware: binary too short (minimum {MIN_FIRMWARE_SIZE} bytes required)"
            )

        # Read and verify magic number at AppInfo offset
        magic_offset = APP_INFO_OFFSET
        magic_bytes = content[magic_offset:magic_offset + 4]
        magic = struct.unpack("<I", magic_bytes)[0]

        if magic != APP_INFO_MAGIC:
            raise ValidationException(
                f"Invalid firmware: magic number mismatch (expected 0x{APP_INFO_MAGIC:08X}, "
                f"got 0x{magic:08X})"
            )

        # Extract version string from AppInfo structure
        version_start = APP_INFO_OFFSET + VERSION_OFFSET_IN_APPINFO
        version_end = version_start + VERSION_MAX_LENGTH
        version_bytes = content[version_start:version_end]

        # Decode as UTF-8 and strip null terminators
        try:
            version = version_bytes.split(b"\x00")[0].decode("utf-8")
        except UnicodeDecodeError as e:
            raise ValidationException(
                f"Invalid firmware: cannot decode version string: {e}"
            ) from e

        if not version:
            raise ValidationException("Invalid firmware: empty version string")

        logger.debug("Extracted firmware version: %s", version)
        return version
