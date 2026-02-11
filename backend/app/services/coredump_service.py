"""Coredump storage service for ESP32 device crash dumps."""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from app.exceptions import InvalidOperationException, ValidationException
from app.utils.fs import atomic_write

logger = logging.getLogger(__name__)

# Maximum coredump size: 1MB
MAX_COREDUMP_SIZE = 1_048_576


class CoredumpService:
    """Service for saving ESP32 coredump files to the filesystem.

    Stores coredump binaries alongside JSON sidecar metadata in
    per-device directories under COREDUMPS_DIR.
    """

    def __init__(self, coredumps_dir: Path | None) -> None:
        """Initialize coredump service.

        Args:
            coredumps_dir: Directory for storing coredump files, or None
                if coredump support is not configured.
        """
        self.coredumps_dir = coredumps_dir
        if coredumps_dir is not None:
            coredumps_dir.mkdir(parents=True, exist_ok=True)
            logger.info("CoredumpService initialized with coredumps_dir: %s", coredumps_dir)
        else:
            logger.info("CoredumpService initialized without coredumps_dir (uploads disabled)")

    def save_coredump(
        self,
        device_key: str,
        model_code: str,
        chip: str,
        firmware_version: str,
        content: bytes,
    ) -> str:
        """Save a coredump binary and its JSON sidecar metadata.

        The coredump is written atomically (temp file + rename) to prevent
        partial writes. A JSON sidecar file with the same base name stores
        metadata about the coredump.

        Args:
            device_key: 8-character device key (determines subdirectory)
            model_code: Device model code
            chip: Chip type (e.g., 'esp32s3')
            firmware_version: Firmware version running on the device
            content: Raw coredump binary data

        Returns:
            The filename of the saved coredump (e.g., 'coredump_20260211T143000_123456Z.dmp')

        Raises:
            InvalidOperationException: If COREDUMPS_DIR is not configured
            ValidationException: If content is empty or exceeds 1MB
        """
        # Guard: coredumps_dir must be configured
        if self.coredumps_dir is None:
            raise InvalidOperationException(
                "upload coredump", "COREDUMPS_DIR is not configured"
            )

        # Validate content
        if not content:
            raise ValidationException("No coredump content provided")

        if len(content) > MAX_COREDUMP_SIZE:
            raise ValidationException("Coredump exceeds maximum size of 1MB")

        # Defense-in-depth: reject device keys with non-alphanumeric characters
        # to prevent path traversal. Device keys are server-generated 8-char
        # alphanumeric strings, but we guard against compromised inputs.
        if not device_key.isalnum():
            raise ValidationException("Invalid device key format")

        # Create per-device directory
        device_dir = self.coredumps_dir / device_key
        device_dir.mkdir(parents=True, exist_ok=True)

        # Generate filename with microsecond precision to avoid collisions
        now = datetime.now(UTC)
        timestamp = now.strftime("%Y%m%dT%H%M%S") + f"_{now.microsecond:06d}Z"
        base_name = f"coredump_{timestamp}"
        dmp_filename = f"{base_name}.dmp"
        json_filename = f"{base_name}.json"

        dmp_path = device_dir / dmp_filename
        json_path = device_dir / json_filename

        # Write coredump binary atomically
        atomic_write(dmp_path, content, device_dir)

        # Write JSON sidecar metadata atomically
        sidecar = {
            "chip": chip,
            "firmware_version": firmware_version,
            "device_key": device_key,
            "model_code": model_code,
            "uploaded_at": now.isoformat(),
        }
        atomic_write(json_path, json.dumps(sidecar, indent=2).encode("utf-8"), device_dir)

        logger.info(
            "Saved coredump for device %s (model=%s, chip=%s, fw=%s): %s",
            device_key,
            model_code,
            chip,
            firmware_version,
            dmp_filename,
        )

        return dmp_filename
