"""Firmware management service for device models."""

import json
import logging
import shutil
import struct
import zipfile
from io import BytesIO
from pathlib import Path

from app.exceptions import RecordNotFoundException, ValidationException
from app.utils.fs import atomic_write

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

# ZIP magic bytes (PK\x03\x04)
ZIP_MAGIC = b"\x50\x4b\x03\x04"

# Required files in a firmware ZIP (model_code is substituted at validation time)
REQUIRED_ZIP_FILES = {"{model_code}.bin", "{model_code}.elf", "{model_code}.map", "sdkconfig", "version.json"}


def is_zip_content(content: bytes) -> bool:
    """Check if content starts with ZIP magic bytes.

    Args:
        content: Raw binary content

    Returns:
        True if the content starts with the ZIP magic header
    """
    return len(content) >= 4 and content[:4] == ZIP_MAGIC


class FirmwareService:
    """Service for managing firmware files for device models.

    Handles firmware upload, download, and version extraction from ESP32 binaries.
    Supports both legacy flat .bin storage and versioned ZIP bundles.

    Storage layout:
    - Legacy flat: ASSETS_DIR/firmware-{model_code}.bin
    - Versioned ZIP: ASSETS_DIR/{model_code}/firmware-{version}.zip
    """

    def __init__(self, assets_dir: Path) -> None:
        """Initialize firmware service.

        Args:
            assets_dir: Directory for storing firmware files
        """
        self.assets_dir = assets_dir
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        logger.info("FirmwareService initialized with assets_dir: %s", assets_dir)

    def get_firmware_path(self, model_code: str) -> Path:
        """Get the legacy flat filesystem path for a model's firmware.

        Args:
            model_code: The device model code

        Returns:
            Path to the firmware file
        """
        return self.assets_dir / f"firmware-{model_code}.bin"

    def get_versioned_zip_path(self, model_code: str, firmware_version: str) -> Path:
        """Get the versioned ZIP path for a model's firmware.

        Args:
            model_code: The device model code
            firmware_version: The firmware version string

        Returns:
            Path to the versioned ZIP file
        """
        return self.assets_dir / model_code / f"firmware-{firmware_version}.zip"

    def firmware_exists(self, model_code: str) -> bool:
        """Check if firmware exists for a model.

        Checks the legacy flat .bin path first, then looks for any versioned
        ZIP in the model subdirectory.

        Args:
            model_code: The device model code

        Returns:
            True if firmware file exists (legacy or versioned)
        """
        if self.get_firmware_path(model_code).exists():
            return True
        model_dir = self.assets_dir / model_code
        return model_dir.exists() and any(model_dir.glob("firmware-*.zip"))

    def get_firmware_stream(
        self, model_code: str, firmware_version: str | None = None
    ) -> BytesIO:
        """Get firmware as a BytesIO stream.

        Tries the versioned ZIP first (if firmware_version is provided), extracting
        the .bin from the archive. Falls back to the legacy flat .bin file.

        Args:
            model_code: The device model code
            firmware_version: Optional firmware version to locate a versioned ZIP

        Returns:
            BytesIO containing the firmware .bin data (seeked to position 0)

        Raises:
            RecordNotFoundException: If firmware doesn't exist
        """
        # Try versioned ZIP first if firmware_version is provided
        if firmware_version:
            zip_path = self.get_versioned_zip_path(model_code, firmware_version)
            if zip_path.exists():
                try:
                    with zipfile.ZipFile(zip_path, "r") as zf:
                        bin_name = f"{model_code}.bin"
                        bin_data = zf.read(bin_name)
                        return BytesIO(bin_data)
                except (zipfile.BadZipFile, KeyError) as e:
                    logger.warning(
                        "Failed to extract .bin from versioned ZIP %s: %s", zip_path, e
                    )
                    # Fall through to legacy path

        # Fall back to legacy flat .bin
        path = self.get_firmware_path(model_code)
        if not path.exists():
            raise RecordNotFoundException("Firmware", model_code)

        return BytesIO(path.read_bytes())

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
        atomic_write(target_path, content, self.assets_dir)
        logger.info("Saved firmware for model %s, version %s", model_code, version)

        return version

    def save_firmware_zip(self, model_code: str, content: bytes) -> str:
        """Save a firmware ZIP bundle and extract version.

        Validates that the ZIP contains exactly the required files, extracts
        the firmware version from the .bin inside, stores the ZIP at the
        versioned path, and also updates the legacy flat .bin for backward
        compatibility.

        Args:
            model_code: The device model code
            content: ZIP file content

        Returns:
            Extracted firmware version string

        Raises:
            ValidationException: If ZIP structure is invalid or .bin is invalid
        """
        # Open ZIP in memory and validate structure
        try:
            zf = zipfile.ZipFile(BytesIO(content), "r")
        except zipfile.BadZipFile as e:
            raise ValidationException(f"Invalid firmware ZIP: {e}") from e

        with zf:
            # Build the expected file set for this model
            expected_files = {
                name.format(model_code=model_code) for name in REQUIRED_ZIP_FILES
            }
            actual_files = set(zf.namelist())

            # Check for missing files
            missing = expected_files - actual_files
            if missing:
                raise ValidationException(
                    f"Invalid firmware ZIP: missing {', '.join(sorted(missing))}"
                )

            # Check for extra unexpected files
            extra = actual_files - expected_files
            if extra:
                raise ValidationException(
                    f"Invalid firmware ZIP: unexpected files: {', '.join(sorted(extra))}"
                )

            # Validate version.json is valid JSON with expected fields
            try:
                version_json_data = json.loads(zf.read("version.json"))
            except (json.JSONDecodeError, KeyError) as e:
                raise ValidationException(
                    f"Invalid firmware ZIP: version.json is not valid JSON: {e}"
                ) from e

            # Check required fields in version.json
            required_fields = {"git_commit", "idf_version", "firmware_version"}
            missing_fields = required_fields - set(version_json_data.keys())
            if missing_fields:
                raise ValidationException(
                    f"Invalid firmware ZIP: version.json missing fields: {', '.join(sorted(missing_fields))}"
                )

            # Extract .bin and validate ESP32 format / extract version
            bin_name = f"{model_code}.bin"
            bin_content = zf.read(bin_name)
            version = self.extract_version(bin_content)

        # Create model subdirectory for versioned storage
        model_dir = self.assets_dir / model_code
        model_dir.mkdir(parents=True, exist_ok=True)

        # Write ZIP atomically to versioned path
        zip_target = self.get_versioned_zip_path(model_code, version)
        atomic_write(zip_target, content, model_dir)

        # Also update legacy flat .bin for backward compatibility
        legacy_target = self.get_firmware_path(model_code)
        atomic_write(legacy_target, bin_content, self.assets_dir)

        logger.info(
            "Saved firmware ZIP for model %s, version %s (ZIP: %s, legacy .bin updated)",
            model_code,
            version,
            zip_target,
        )

        return version

    def delete_firmware(self, model_code: str) -> None:
        """Delete firmware files for a model.

        Removes both the legacy flat .bin and the versioned ZIP directory.
        Best-effort deletion - logs errors but doesn't raise.

        Args:
            model_code: The device model code
        """
        # Remove legacy flat .bin
        path = self.get_firmware_path(model_code)
        if path.exists():
            try:
                path.unlink()
                logger.info("Deleted legacy firmware for model %s", model_code)
            except OSError as e:
                logger.warning("Failed to delete legacy firmware for %s: %s", model_code, e)

        # Remove versioned ZIP directory
        model_dir = self.assets_dir / model_code
        if model_dir.exists() and model_dir.is_dir():
            try:
                shutil.rmtree(model_dir)
                logger.info("Deleted versioned firmware directory for model %s", model_code)
            except OSError as e:
                logger.warning("Failed to delete versioned dir for %s: %s", model_code, e)

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
