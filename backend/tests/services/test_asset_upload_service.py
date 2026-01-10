"""Tests for AssetUploadService."""

import base64
import io
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from app.exceptions import ValidationException
from app.services.asset_upload_service import AssetUploadService


@pytest.fixture
def assets_dir(tmp_path: Path) -> Path:
    """Create temporary assets directory."""
    return tmp_path


@pytest.fixture
def test_keypair() -> tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]:
    """Generate test RSA keypair."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    return private_key, public_key


@pytest.fixture
def signing_key_path(tmp_path: Path, test_keypair: tuple) -> Path:
    """Create signing key file."""
    private_key, _ = test_keypair
    key_path = tmp_path / "test_signing_key.pem"

    # Write private key in PEM format
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    key_path.write_bytes(pem)

    return key_path


@pytest.fixture
def service(
    assets_dir: Path, signing_key_path: Path
) -> AssetUploadService:
    """Create AssetUploadService instance."""
    return AssetUploadService(
        assets_dir=assets_dir,
        signing_key_path=signing_key_path,
        timestamp_tolerance_seconds=300,
    )


@pytest.fixture
def sign_timestamp(test_keypair: tuple):
    """Factory fixture for signing timestamps."""
    private_key, _ = test_keypair

    def _sign(timestamp_str: str) -> str:
        signature = private_key.sign(
            timestamp_str.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256()
        )
        return base64.b64encode(signature).decode("ascii")

    return _sign


class TestServiceInitialization:
    """Tests for service initialization."""

    def test_init_success(self, assets_dir: Path, signing_key_path: Path):
        """Service initializes with valid configuration."""
        service = AssetUploadService(
            assets_dir=assets_dir,
            signing_key_path=signing_key_path,
            timestamp_tolerance_seconds=300,
        )

        assert service.assets_dir == assets_dir
        assert service.timestamp_tolerance_seconds == 300
        assert hasattr(service, "public_key")

    def test_init_missing_key_file(self, assets_dir: Path, tmp_path: Path):
        """Service fails to initialize with missing key file."""
        nonexistent_key = tmp_path / "nonexistent.pem"

        with pytest.raises(ValueError, match="Signing key file not found"):
            AssetUploadService(
                assets_dir=assets_dir,
                signing_key_path=nonexistent_key,
                timestamp_tolerance_seconds=300,
            )

    def test_init_invalid_key_file(self, assets_dir: Path, tmp_path: Path):
        """Service fails to initialize with invalid key file."""
        invalid_key = tmp_path / "invalid.pem"
        invalid_key.write_text("not a valid PEM key")

        with pytest.raises(ValueError, match="Failed to load signing key"):
            AssetUploadService(
                assets_dir=assets_dir,
                signing_key_path=invalid_key,
                timestamp_tolerance_seconds=300,
            )

    def test_init_nonexistent_assets_dir(self, signing_key_path: Path, tmp_path: Path):
        """Service fails to initialize with nonexistent assets directory."""
        nonexistent_dir = tmp_path / "nonexistent"

        with pytest.raises(ValueError, match="Assets directory does not exist"):
            AssetUploadService(
                assets_dir=nonexistent_dir,
                signing_key_path=signing_key_path,
                timestamp_tolerance_seconds=300,
            )

    def test_init_assets_dir_is_file(
        self, signing_key_path: Path, tmp_path: Path
    ):
        """Service fails to initialize when assets path is a file."""
        file_path = tmp_path / "file.txt"
        file_path.write_text("test")

        with pytest.raises(ValueError, match="Assets path is not a directory"):
            AssetUploadService(
                assets_dir=file_path,
                signing_key_path=signing_key_path,
                timestamp_tolerance_seconds=300,
            )


class TestValidateFilename:
    """Tests for filename validation."""

    def test_valid_filename(self, service: AssetUploadService):
        """Valid filename passes validation."""
        service.validate_filename("firmware.bin")
        service.validate_filename("image.jpg")
        service.validate_filename("config-v2.json")

    def test_path_traversal_rejected(self, service: AssetUploadService):
        """Filename with .. is rejected."""
        with pytest.raises(ValidationException, match="path traversal not allowed"):
            service.validate_filename("../etc/passwd")

        with pytest.raises(ValidationException, match="path traversal not allowed"):
            service.validate_filename("../../etc/passwd")

        with pytest.raises(ValidationException, match="path traversal not allowed"):
            service.validate_filename("file..name")

    def test_forward_slash_rejected(self, service: AssetUploadService):
        """Filename with forward slash is rejected."""
        with pytest.raises(
            ValidationException, match="directory separators not allowed"
        ):
            service.validate_filename("subdir/firmware.bin")

        with pytest.raises(
            ValidationException, match="directory separators not allowed"
        ):
            service.validate_filename("/etc/passwd")

    def test_backslash_rejected(self, service: AssetUploadService):
        """Filename with backslash is rejected."""
        with pytest.raises(
            ValidationException, match="directory separators not allowed"
        ):
            service.validate_filename("subdir\\firmware.bin")

        with pytest.raises(
            ValidationException, match="directory separators not allowed"
        ):
            service.validate_filename("C:\\Windows\\system32")

    def test_empty_filename_rejected(self, service: AssetUploadService):
        """Empty filename is rejected."""
        with pytest.raises(ValidationException, match="filename cannot be empty"):
            service.validate_filename("")

        with pytest.raises(ValidationException, match="filename cannot be empty"):
            service.validate_filename("   ")


class TestValidateTimestamp:
    """Tests for timestamp validation."""

    def test_valid_timestamp_current(self, service: AssetUploadService):
        """Current timestamp passes validation."""
        now = datetime.now(UTC)
        timestamp_str = now.isoformat()

        result = service.validate_timestamp(timestamp_str)

        assert isinstance(result, datetime)
        assert result.tzinfo is not None

    def test_valid_timestamp_within_tolerance_past(self, service: AssetUploadService):
        """Timestamp 299 seconds in past passes validation."""
        past = datetime.now(UTC) - timedelta(seconds=299)
        timestamp_str = past.isoformat()

        result = service.validate_timestamp(timestamp_str)

        assert isinstance(result, datetime)

    def test_valid_timestamp_within_tolerance_future(
        self, service: AssetUploadService
    ):
        """Timestamp 299 seconds in future passes validation."""
        future = datetime.now(UTC) + timedelta(seconds=299)
        timestamp_str = future.isoformat()

        result = service.validate_timestamp(timestamp_str)

        assert isinstance(result, datetime)

    def test_timestamp_outside_tolerance_past(self, service: AssetUploadService):
        """Timestamp 301 seconds in past is rejected."""
        past = datetime.now(UTC) - timedelta(seconds=301)
        timestamp_str = past.isoformat()

        with pytest.raises(ValidationException, match="must be within"):
            service.validate_timestamp(timestamp_str)

    def test_timestamp_outside_tolerance_future(self, service: AssetUploadService):
        """Timestamp 301 seconds in future is rejected."""
        future = datetime.now(UTC) + timedelta(seconds=301)
        timestamp_str = future.isoformat()

        with pytest.raises(ValidationException, match="must be within"):
            service.validate_timestamp(timestamp_str)

    def test_invalid_timestamp_format(self, service: AssetUploadService):
        """Non-ISO8601 timestamp is rejected."""
        with pytest.raises(ValidationException, match="Invalid timestamp format"):
            service.validate_timestamp("not-a-date")

        with pytest.raises(ValidationException, match="Invalid timestamp format"):
            service.validate_timestamp("2026-13-45")

    def test_timestamp_without_timezone(self, service: AssetUploadService):
        """Timestamp without timezone is accepted and treated as UTC."""
        now = datetime.now(UTC)
        timestamp_str = now.replace(tzinfo=None).isoformat()

        result = service.validate_timestamp(timestamp_str)

        # Should be converted to UTC
        assert result.tzinfo is not None


class TestVerifySignature:
    """Tests for signature verification."""

    def test_valid_signature(self, service: AssetUploadService, sign_timestamp):
        """Valid signature passes verification."""
        timestamp_str = "2026-01-09T14:30:00"
        signature_str = sign_timestamp(timestamp_str)

        # Should not raise
        service.verify_signature(timestamp_str, signature_str)

    def test_invalid_signature(self, service: AssetUploadService):
        """Invalid signature is rejected."""
        timestamp_str = "2026-01-09T14:30:00"
        invalid_signature = base64.b64encode(b"invalid signature").decode("ascii")

        with pytest.raises(
            ValidationException, match="cryptographic verification failed"
        ):
            service.verify_signature(timestamp_str, invalid_signature)

    def test_tampered_timestamp(self, service: AssetUploadService, sign_timestamp):
        """Signature for different timestamp is rejected."""
        original_timestamp = "2026-01-09T14:30:00"
        signature_str = sign_timestamp(original_timestamp)

        tampered_timestamp = "2026-01-09T15:30:00"

        with pytest.raises(
            ValidationException, match="cryptographic verification failed"
        ):
            service.verify_signature(tampered_timestamp, signature_str)

    def test_non_base64_signature(self, service: AssetUploadService):
        """Non-base64 signature is rejected."""
        timestamp_str = "2026-01-09T14:30:00"
        invalid_base64 = "not base64!!!"

        with pytest.raises(ValidationException, match="expected base64-encoded string"):
            service.verify_signature(timestamp_str, invalid_base64)

    def test_empty_signature(self, service: AssetUploadService):
        """Empty signature is rejected."""
        timestamp_str = "2026-01-09T14:30:00"

        # Empty string is valid base64 (decodes to empty bytes), so it fails on verification
        with pytest.raises(ValidationException, match="cryptographic verification failed"):
            service.verify_signature(timestamp_str, "")


class TestSaveFile:
    """Tests for file saving."""

    def test_save_file_success(self, service: AssetUploadService, assets_dir: Path):
        """File is saved successfully."""
        filename = "test.bin"
        content = b"test file content"
        file_data = io.BytesIO(content)

        saved_path, file_size = service.save_file(filename, file_data)

        assert saved_path == assets_dir / filename
        assert file_size == len(content)
        assert saved_path.exists()
        assert saved_path.read_bytes() == content

    def test_save_file_overwrites_existing(
        self, service: AssetUploadService, assets_dir: Path
    ):
        """Uploading same filename overwrites existing file."""
        filename = "test.bin"

        # Create existing file
        existing_path = assets_dir / filename
        existing_path.write_bytes(b"old content")

        # Upload new file
        new_content = b"new content"
        file_data = io.BytesIO(new_content)

        saved_path, file_size = service.save_file(filename, file_data)

        assert saved_path.read_bytes() == new_content
        assert file_size == len(new_content)

    def test_save_large_file(self, service: AssetUploadService, assets_dir: Path):
        """Large file is saved successfully in chunks."""
        filename = "large.bin"
        # Create 100KB file
        content = b"x" * 100000
        file_data = io.BytesIO(content)

        saved_path, file_size = service.save_file(filename, file_data)

        assert file_size == len(content)
        assert saved_path.read_bytes() == content


class TestUploadAsset:
    """Tests for complete upload flow."""

    def test_upload_asset_success(self, service: AssetUploadService, sign_timestamp):
        """Complete upload with all validations passes."""
        filename = "firmware.bin"
        content = b"firmware data"
        file_data = io.BytesIO(content)

        timestamp_str = datetime.now(UTC).isoformat()
        signature_str = sign_timestamp(timestamp_str)

        saved_path, file_size, upload_time = service.upload_asset(
            filename=filename,
            timestamp_str=timestamp_str,
            signature_str=signature_str,
            file_data=file_data,
        )

        assert saved_path.exists()
        assert file_size == len(content)
        assert isinstance(upload_time, datetime)

    def test_upload_asset_invalid_filename(
        self, service: AssetUploadService, sign_timestamp
    ):
        """Upload fails on filename validation."""
        filename = "../etc/passwd"
        file_data = io.BytesIO(b"test")

        timestamp_str = datetime.now(UTC).isoformat()
        signature_str = sign_timestamp(timestamp_str)

        with pytest.raises(ValidationException, match="path traversal"):
            service.upload_asset(
                filename=filename,
                timestamp_str=timestamp_str,
                signature_str=signature_str,
                file_data=file_data,
            )

    def test_upload_asset_invalid_timestamp(
        self, service: AssetUploadService, sign_timestamp
    ):
        """Upload fails on timestamp validation."""
        filename = "firmware.bin"
        file_data = io.BytesIO(b"test")

        # Timestamp 400 seconds in past (outside tolerance)
        timestamp = datetime.now(UTC) - timedelta(seconds=400)
        timestamp_str = timestamp.isoformat()
        signature_str = sign_timestamp(timestamp_str)

        with pytest.raises(ValidationException, match="must be within"):
            service.upload_asset(
                filename=filename,
                timestamp_str=timestamp_str,
                signature_str=signature_str,
                file_data=file_data,
            )

    def test_upload_asset_invalid_signature(self, service: AssetUploadService):
        """Upload fails on signature verification."""
        filename = "firmware.bin"
        file_data = io.BytesIO(b"test")

        timestamp_str = datetime.now(UTC).isoformat()
        invalid_signature = base64.b64encode(b"invalid").decode("ascii")

        with pytest.raises(ValidationException, match="cryptographic verification"):
            service.upload_asset(
                filename=filename,
                timestamp_str=timestamp_str,
                signature_str=invalid_signature,
                file_data=file_data,
            )

    def test_upload_asset_validation_order(
        self, service: AssetUploadService, sign_timestamp
    ):
        """Validations happen in correct order (filename -> timestamp -> signature)."""
        # Invalid filename should fail first, even with invalid timestamp/signature
        filename = "../etc/passwd"
        file_data = io.BytesIO(b"test")

        # Use invalid timestamp and signature
        timestamp_str = "not-a-date"
        signature_str = "invalid"

        with pytest.raises(ValidationException, match="path traversal"):
            service.upload_asset(
                filename=filename,
                timestamp_str=timestamp_str,
                signature_str=signature_str,
                file_data=file_data,
            )
