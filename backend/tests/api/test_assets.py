"""Tests for asset upload API endpoints."""

import base64
import io
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from flask import Flask
from flask.testing import FlaskClient

from app.config import Settings


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
def test_settings_with_assets(
    config_dir: Path, assets_dir: Path, signing_key_path: Path
) -> Settings:
    """Create test settings with asset upload configuration."""
    return Settings(
        ESP32_CONFIGS_DIR=config_dir,
        ASSETS_DIR=assets_dir,
        SIGNING_KEY_PATH=signing_key_path,
        TIMESTAMP_TOLERANCE_SECONDS=300,
        SECRET_KEY="test-secret-key",
        DEBUG=True,
        CORS_ORIGINS=["http://localhost:3000"],
    )


@pytest.fixture
def app_with_assets(test_settings_with_assets: Settings) -> Flask:
    """Create Flask app with asset upload configuration."""
    from app import create_app

    return create_app(test_settings_with_assets)


@pytest.fixture
def client_with_assets(app_with_assets: Flask) -> FlaskClient:
    """Create test client with asset upload support."""
    return app_with_assets.test_client()


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


class TestUploadAsset:
    """Tests for POST /api/assets endpoint."""

    def test_upload_asset_success(self, client_with_assets: FlaskClient, sign_timestamp):
        """Valid upload returns 200 with metadata."""
        timestamp_str = datetime.now(UTC).isoformat()
        signature_str = sign_timestamp(timestamp_str)

        file_content = b"test firmware data"
        file_data = (io.BytesIO(file_content), "firmware.bin")

        response = client_with_assets.post(
            "/api/assets",
            data={
                "file": file_data,
                "timestamp": timestamp_str,
                "signature": signature_str,
            },
            content_type="multipart/form-data",
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data["filename"] == "firmware.bin"
        assert data["size"] == len(file_content)
        assert "uploaded_at" in data

    def test_upload_asset_missing_file(
        self, client_with_assets: FlaskClient, sign_timestamp
    ):
        """Missing file field returns 400."""
        timestamp_str = datetime.now(UTC).isoformat()
        signature_str = sign_timestamp(timestamp_str)

        response = client_with_assets.post(
            "/api/assets",
            data={"timestamp": timestamp_str, "signature": signature_str},
            content_type="multipart/form-data",
        )

        assert response.status_code == 400
        data = response.get_json()
        assert "error" in data
        assert "file" in data["error"].lower()
        assert data["code"] == "VALIDATION_FAILED"

    def test_upload_asset_missing_timestamp(self, client_with_assets: FlaskClient):
        """Missing timestamp field returns 400."""
        file_data = (io.BytesIO(b"test"), "firmware.bin")

        response = client_with_assets.post(
            "/api/assets",
            data={"file": file_data, "signature": "dummy"},
            content_type="multipart/form-data",
        )

        assert response.status_code == 400
        data = response.get_json()
        assert "error" in data
        assert "timestamp" in data["error"].lower()
        assert data["code"] == "VALIDATION_FAILED"

    def test_upload_asset_missing_signature(self, client_with_assets: FlaskClient):
        """Missing signature field returns 400."""
        timestamp_str = datetime.now(UTC).isoformat()
        file_data = (io.BytesIO(b"test"), "firmware.bin")

        response = client_with_assets.post(
            "/api/assets",
            data={"file": file_data, "timestamp": timestamp_str},
            content_type="multipart/form-data",
        )

        assert response.status_code == 400
        data = response.get_json()
        assert "error" in data
        assert "signature" in data["error"].lower()
        assert data["code"] == "VALIDATION_FAILED"

    def test_upload_asset_invalid_filename(
        self, client_with_assets: FlaskClient, sign_timestamp
    ):
        """Filename with path traversal returns 400."""
        timestamp_str = datetime.now(UTC).isoformat()
        signature_str = sign_timestamp(timestamp_str)

        file_data = (io.BytesIO(b"test"), "../etc/passwd")

        response = client_with_assets.post(
            "/api/assets",
            data={
                "file": file_data,
                "timestamp": timestamp_str,
                "signature": signature_str,
            },
            content_type="multipart/form-data",
        )

        assert response.status_code == 400
        data = response.get_json()
        assert "error" in data
        assert "filename" in data["error"].lower()
        assert data["code"] == "VALIDATION_FAILED"

    def test_upload_asset_invalid_timestamp_format(
        self, client_with_assets: FlaskClient, sign_timestamp
    ):
        """Invalid timestamp format returns 400."""
        timestamp_str = "not-a-date"
        signature_str = sign_timestamp(timestamp_str)

        file_data = (io.BytesIO(b"test"), "firmware.bin")

        response = client_with_assets.post(
            "/api/assets",
            data={
                "file": file_data,
                "timestamp": timestamp_str,
                "signature": signature_str,
            },
            content_type="multipart/form-data",
        )

        assert response.status_code == 400
        data = response.get_json()
        assert "error" in data
        assert "timestamp" in data["error"].lower()
        assert data["code"] == "VALIDATION_FAILED"

    def test_upload_asset_timestamp_outside_tolerance(
        self, client_with_assets: FlaskClient, sign_timestamp
    ):
        """Timestamp outside tolerance window returns 400."""
        # Timestamp 400 seconds in past
        old_timestamp = datetime.now(UTC) - timedelta(seconds=400)
        timestamp_str = old_timestamp.isoformat()
        signature_str = sign_timestamp(timestamp_str)

        file_data = (io.BytesIO(b"test"), "firmware.bin")

        response = client_with_assets.post(
            "/api/assets",
            data={
                "file": file_data,
                "timestamp": timestamp_str,
                "signature": signature_str,
            },
            content_type="multipart/form-data",
        )

        assert response.status_code == 400
        data = response.get_json()
        assert "error" in data
        assert "timestamp" in data["error"].lower()
        assert data["code"] == "VALIDATION_FAILED"

    def test_upload_asset_invalid_signature(self, client_with_assets: FlaskClient):
        """Invalid signature returns 400."""
        timestamp_str = datetime.now(UTC).isoformat()
        invalid_signature = base64.b64encode(b"invalid").decode("ascii")

        file_data = (io.BytesIO(b"test"), "firmware.bin")

        response = client_with_assets.post(
            "/api/assets",
            data={
                "file": file_data,
                "timestamp": timestamp_str,
                "signature": invalid_signature,
            },
            content_type="multipart/form-data",
        )

        assert response.status_code == 400
        data = response.get_json()
        assert "error" in data
        assert "signature" in data["error"].lower()
        assert data["code"] == "VALIDATION_FAILED"

    def test_upload_asset_tampered_timestamp(
        self, client_with_assets: FlaskClient, sign_timestamp
    ):
        """Signature for different timestamp returns 400."""
        original_timestamp = datetime.now(UTC).isoformat()
        signature_str = sign_timestamp(original_timestamp)

        # Use different timestamp than signed
        tampered_timestamp = (
            datetime.now(UTC) + timedelta(seconds=10)
        ).isoformat()

        file_data = (io.BytesIO(b"test"), "firmware.bin")

        response = client_with_assets.post(
            "/api/assets",
            data={
                "file": file_data,
                "timestamp": tampered_timestamp,
                "signature": signature_str,
            },
            content_type="multipart/form-data",
        )

        assert response.status_code == 400
        data = response.get_json()
        assert "error" in data
        assert "signature" in data["error"].lower()
        assert data["code"] == "VALIDATION_FAILED"

    def test_upload_asset_overwrites_existing(
        self, client_with_assets: FlaskClient, sign_timestamp, assets_dir: Path
    ):
        """Uploading same filename overwrites existing file."""
        filename = "firmware.bin"

        # First upload
        timestamp_str = datetime.now(UTC).isoformat()
        signature_str = sign_timestamp(timestamp_str)
        file1_content = b"first version"
        file1_data = (io.BytesIO(file1_content), filename)

        response1 = client_with_assets.post(
            "/api/assets",
            data={
                "file": file1_data,
                "timestamp": timestamp_str,
                "signature": signature_str,
            },
            content_type="multipart/form-data",
        )

        assert response1.status_code == 200

        # Second upload with same filename
        timestamp_str2 = datetime.now(UTC).isoformat()
        signature_str2 = sign_timestamp(timestamp_str2)
        file2_content = b"second version"
        file2_data = (io.BytesIO(file2_content), filename)

        response2 = client_with_assets.post(
            "/api/assets",
            data={
                "file": file2_data,
                "timestamp": timestamp_str2,
                "signature": signature_str2,
            },
            content_type="multipart/form-data",
        )

        assert response2.status_code == 200

        # Verify file was overwritten
        saved_file = assets_dir / filename
        assert saved_file.read_bytes() == file2_content

    def test_upload_asset_multiple_files(
        self, client_with_assets: FlaskClient, sign_timestamp
    ):
        """Multiple different files can be uploaded."""
        files = [
            ("file1.bin", b"content1"),
            ("file2.bin", b"content2"),
            ("file3.bin", b"content3"),
        ]

        for filename, content in files:
            timestamp_str = datetime.now(UTC).isoformat()
            signature_str = sign_timestamp(timestamp_str)
            file_data = (io.BytesIO(content), filename)

            response = client_with_assets.post(
                "/api/assets",
                data={
                    "file": file_data,
                    "timestamp": timestamp_str,
                    "signature": signature_str,
                },
                content_type="multipart/form-data",
            )

            assert response.status_code == 200
            data = response.get_json()
            assert data["filename"] == filename
            assert data["size"] == len(content)

    def test_upload_asset_empty_file(
        self, client_with_assets: FlaskClient, sign_timestamp
    ):
        """Empty file can be uploaded."""
        timestamp_str = datetime.now(UTC).isoformat()
        signature_str = sign_timestamp(timestamp_str)

        file_data = (io.BytesIO(b""), "empty.bin")

        response = client_with_assets.post(
            "/api/assets",
            data={
                "file": file_data,
                "timestamp": timestamp_str,
                "signature": signature_str,
            },
            content_type="multipart/form-data",
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data["filename"] == "empty.bin"
        assert data["size"] == 0

    def test_upload_asset_large_file(
        self, client_with_assets: FlaskClient, sign_timestamp
    ):
        """Large file can be uploaded."""
        timestamp_str = datetime.now(UTC).isoformat()
        signature_str = sign_timestamp(timestamp_str)

        # 1MB file
        large_content = b"x" * (1024 * 1024)
        file_data = (io.BytesIO(large_content), "large.bin")

        response = client_with_assets.post(
            "/api/assets",
            data={
                "file": file_data,
                "timestamp": timestamp_str,
                "signature": signature_str,
            },
            content_type="multipart/form-data",
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data["filename"] == "large.bin"
        assert data["size"] == len(large_content)


class TestAssetsWithMqtt:
    """Tests for MQTT integration in asset upload API endpoints."""

    def test_upload_asset_publishes_mqtt_notification(
        self, app_with_assets: Flask, client_with_assets: FlaskClient, sign_timestamp
    ):
        """Successful asset upload publishes MQTT notification."""
        container = app_with_assets.container
        mqtt_service = container.mqtt_service()

        with patch.object(mqtt_service, "publish_asset_update") as mock_publish:
            timestamp_str = datetime.now(UTC).isoformat()
            signature_str = sign_timestamp(timestamp_str)

            file_content = b"test firmware data"
            file_data = (io.BytesIO(file_content), "firmware.bin")

            response = client_with_assets.post(
                "/api/assets",
                data={
                    "file": file_data,
                    "timestamp": timestamp_str,
                    "signature": signature_str,
                },
                content_type="multipart/form-data",
            )

            assert response.status_code == 200

            # Verify MQTT notification was published with correct filename
            mock_publish.assert_called_once_with("firmware.bin")

    def test_upload_asset_with_different_filenames_publishes_correctly(
        self, app_with_assets: Flask, client_with_assets: FlaskClient, sign_timestamp
    ):
        """Different asset filenames are published correctly."""
        container = app_with_assets.container
        mqtt_service = container.mqtt_service()

        filenames = ["firmware-v1.2.3.bin", "config.json", "image.png"]

        for filename in filenames:
            with patch.object(mqtt_service, "publish_asset_update") as mock_publish:
                timestamp_str = datetime.now(UTC).isoformat()
                signature_str = sign_timestamp(timestamp_str)
                file_data = (io.BytesIO(b"test"), filename)

                response = client_with_assets.post(
                    "/api/assets",
                    data={
                        "file": file_data,
                        "timestamp": timestamp_str,
                        "signature": signature_str,
                    },
                    content_type="multipart/form-data",
                )

                assert response.status_code == 200
                mock_publish.assert_called_once_with(filename)

    def test_upload_asset_failure_does_not_publish_mqtt(
        self, app_with_assets: Flask, client_with_assets: FlaskClient
    ):
        """Failed asset upload does not publish MQTT notification."""
        container = app_with_assets.container
        mqtt_service = container.mqtt_service()

        with patch.object(mqtt_service, "publish_asset_update") as mock_publish:
            # Invalid request - missing timestamp
            file_data = (io.BytesIO(b"test"), "firmware.bin")

            response = client_with_assets.post(
                "/api/assets",
                data={"file": file_data, "signature": "dummy"},
                content_type="multipart/form-data",
            )

            assert response.status_code == 400

            # MQTT should not be published on failure
            mock_publish.assert_not_called()

    def test_upload_asset_validation_error_does_not_publish_mqtt(
        self, app_with_assets: Flask, client_with_assets: FlaskClient, sign_timestamp
    ):
        """Validation errors do not publish MQTT notification."""
        container = app_with_assets.container
        mqtt_service = container.mqtt_service()

        with patch.object(mqtt_service, "publish_asset_update") as mock_publish:
            timestamp_str = datetime.now(UTC).isoformat()
            signature_str = sign_timestamp(timestamp_str)

            # Invalid filename with path traversal
            file_data = (io.BytesIO(b"test"), "../etc/passwd")

            response = client_with_assets.post(
                "/api/assets",
                data={
                    "file": file_data,
                    "timestamp": timestamp_str,
                    "signature": signature_str,
                },
                content_type="multipart/form-data",
            )

            assert response.status_code == 400

            # MQTT should not be published on validation failure
            mock_publish.assert_not_called()

    def test_upload_asset_mqtt_disabled_succeeds(
        self, app_with_assets: Flask, client_with_assets: FlaskClient, sign_timestamp
    ):
        """Asset upload succeeds when MQTT is disabled."""
        container = app_with_assets.container
        mqtt_service = container.mqtt_service()

        # Disable MQTT by setting enabled flag
        mqtt_service.enabled = False

        timestamp_str = datetime.now(UTC).isoformat()
        signature_str = sign_timestamp(timestamp_str)

        file_content = b"test firmware data"
        file_data = (io.BytesIO(file_content), "firmware.bin")

        response = client_with_assets.post(
            "/api/assets",
            data={
                "file": file_data,
                "timestamp": timestamp_str,
                "signature": signature_str,
            },
            content_type="multipart/form-data",
        )

        # API should return success when MQTT is disabled
        assert response.status_code == 200
