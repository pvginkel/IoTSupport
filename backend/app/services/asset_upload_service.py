"""Asset upload service for managing cryptographically-signed device uploads."""

import base64
import binascii
import logging
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from app.exceptions import ValidationException

logger = logging.getLogger(__name__)


class AssetUploadService:
    """Service for validating and storing cryptographically-signed asset uploads.

    This service validates filenames, timestamps, and RSA signatures before
    accepting file uploads from IoT devices. The signing key is loaded once
    at initialization and cached for the lifetime of the service.

    Security model: This uses a shared-key model where trusted devices possess
    the private key and the server extracts the public key for verification.
    The PHP implementation loads a private key and extracts the public key from it.
    """

    def __init__(
        self,
        assets_dir: Path,
        signing_key_path: Path,
        timestamp_tolerance_seconds: int,
    ) -> None:
        """Initialize service with configuration.

        Args:
            assets_dir: Directory where uploaded files will be stored
            signing_key_path: Path to RSA signing key file (PEM format)
            timestamp_tolerance_seconds: Maximum allowed timestamp drift

        Raises:
            ValueError: If signing key cannot be loaded or assets directory is invalid
        """
        self.assets_dir = assets_dir
        self.timestamp_tolerance_seconds = timestamp_tolerance_seconds

        # Load and cache the RSA key at initialization
        try:
            with open(signing_key_path, "rb") as key_file:
                key_data = key_file.read()

            # Load private key and extract public key (matching PHP behavior)
            private_key = serialization.load_pem_private_key(key_data, password=None)

            if not isinstance(private_key, rsa.RSAPrivateKey):
                raise ValueError("Signing key must be an RSA private key")

            # Extract public key for verification
            self.public_key = private_key.public_key()

            logger.info("Successfully loaded signing key from %s", signing_key_path)

        except FileNotFoundError as e:
            raise ValueError(
                f"Signing key file not found: {signing_key_path}"
            ) from e
        except Exception as e:
            raise ValueError(f"Failed to load signing key: {e}") from e

        # Validate assets directory
        if not self.assets_dir.exists():
            raise ValueError(f"Assets directory does not exist: {self.assets_dir}")
        if not self.assets_dir.is_dir():
            raise ValueError(f"Assets path is not a directory: {self.assets_dir}")

    def validate_filename(self, filename: str) -> None:
        """Validate filename for path traversal prevention.

        Args:
            filename: The filename to validate

        Raises:
            ValidationException: If filename is invalid or contains path traversal
        """
        # Check for empty filename
        if not filename or not filename.strip():
            raise ValidationException("Invalid filename: filename cannot be empty")

        # Check for path traversal sequences
        if ".." in filename:
            raise ValidationException(
                "Invalid filename: path traversal not allowed (..)"
            )

        # Check for directory separators (both forward and backslash)
        if "/" in filename or "\\" in filename:
            raise ValidationException(
                "Invalid filename: directory separators not allowed"
            )

    def validate_timestamp(self, timestamp_str: str) -> datetime:
        """Validate timestamp is within acceptable tolerance window.

        Args:
            timestamp_str: ISO 8601 formatted timestamp string

        Returns:
            Parsed datetime object

        Raises:
            ValidationException: If timestamp format is invalid or outside tolerance
        """
        # Parse ISO 8601 timestamp
        try:
            upload_time = datetime.fromisoformat(timestamp_str)
        except (ValueError, TypeError) as e:
            raise ValidationException(
                f"Invalid timestamp format: expected ISO 8601 format (e.g., '2026-01-09T14:30:00'), got '{timestamp_str}'"
            ) from e

        # Ensure timestamp is timezone-aware (convert to UTC if needed)
        if upload_time.tzinfo is None:
            upload_time = upload_time.replace(tzinfo=UTC)

        # Get current server time
        server_time = datetime.now(UTC)

        # Calculate time difference
        time_diff = abs((server_time - upload_time).total_seconds())

        # Validate within tolerance
        if time_diff > self.timestamp_tolerance_seconds:
            raise ValidationException(
                f"Invalid timestamp: must be within ±{self.timestamp_tolerance_seconds} seconds of server time. "
                f"Server time: {server_time.isoformat()}, Upload time: {upload_time.isoformat()}, "
                f"Difference: {time_diff:.1f}s"
            )

        return upload_time

    def verify_signature(self, timestamp_str: str, signature_str: str) -> None:
        """Verify RSA signature of timestamp.

        Args:
            timestamp_str: The timestamp string that was signed
            signature_str: Base64-encoded RSA signature

        Raises:
            ValidationException: If signature format is invalid or verification fails
        """
        # Decode base64 signature
        try:
            signature_bytes = base64.b64decode(signature_str)
        except (binascii.Error, ValueError) as e:
            raise ValidationException(
                "Invalid signature format: expected base64-encoded string"
            ) from e

        # Verify signature using RSA/SHA256 with PKCS1v15 padding (PHP default)
        try:
            start_time = time.perf_counter()
            self.public_key.verify(
                signature_bytes,
                timestamp_str.encode("utf-8"),
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
            duration = time.perf_counter() - start_time
            logger.debug("Signature verification succeeded in %.3fms", duration * 1000)

        except Exception as e:
            logger.warning(
                "Signature verification failed for timestamp '%s': %s",
                timestamp_str,
                e,
            )
            raise ValidationException(
                "Invalid signature: cryptographic verification failed"
            ) from e

    def save_file(self, filename: str, file_data: BinaryIO) -> tuple[Path, int]:
        """Save uploaded file to assets directory atomically.

        Args:
            filename: Name for the saved file
            file_data: Binary file data stream

        Returns:
            Tuple of (saved file path, file size in bytes)

        Raises:
            OSError: If file write fails
        """
        file_path = self.assets_dir / filename

        # Create temp file in same directory for atomic rename
        temp_path = file_path.with_suffix(".tmp")

        try:
            # Write file data to temp file
            with open(temp_path, "wb") as f:
                # Read in chunks to handle large files
                file_size = 0
                while True:
                    chunk = file_data.read(8192)
                    if not chunk:
                        break
                    f.write(chunk)
                    file_size += len(chunk)

            # Atomic rename (overwrites existing file)
            os.replace(temp_path, file_path)

            logger.info(
                "Saved file '%s' (%d bytes) to %s", filename, file_size, file_path
            )

            return file_path, file_size

        finally:
            # Clean up temp file if rename failed
            if temp_path.exists():
                temp_path.unlink()

    def upload_asset(
        self, filename: str, timestamp_str: str, signature_str: str, file_data: BinaryIO
    ) -> tuple[Path, int, datetime]:
        """Process complete asset upload with validation and storage.

        This is the main entry point that orchestrates all validation steps
        and saves the file if all checks pass.

        Args:
            filename: Filename from upload
            timestamp_str: ISO 8601 timestamp string
            signature_str: Base64-encoded RSA signature
            file_data: Binary file data stream

        Returns:
            Tuple of (saved path, file size, upload timestamp)

        Raises:
            ValidationException: If any validation step fails
            OSError: If file write fails
        """
        # Step 1: Validate filename
        self.validate_filename(filename)

        # Step 2: Validate timestamp
        upload_time = self.validate_timestamp(timestamp_str)

        # Step 3: Verify signature
        self.verify_signature(timestamp_str, signature_str)

        # Step 4: Save file
        file_path, file_size = self.save_file(filename, file_data)

        return file_path, file_size, upload_time
