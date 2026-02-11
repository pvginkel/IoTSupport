"""Tests for pipeline API endpoints."""

import json
import zipfile
from io import BytesIO
from unittest.mock import MagicMock, patch

from flask import Flask
from flask.testing import FlaskClient

from app.config import Settings
from app.services.container import ServiceContainer
from tests.conftest import create_test_firmware


class TestPipelineFirmwareUpload:
    """Tests for POST /api/pipeline/models/<code>/firmware."""

    def test_upload_firmware_by_code_success(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test uploading firmware using model code."""
        with app.app_context():
            model_service = container.device_model_service()
            model_service.create_device_model(code="pipetest", name="Pipeline Test")
            container.db_session().commit()

        firmware_content = create_test_firmware(b"1.0.0")

        response = client.post(
            "/api/pipeline/models/pipetest/firmware",
            data=firmware_content,
            content_type="application/octet-stream",
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data["firmware_version"] == "1.0.0"
        assert data["code"] == "pipetest"

    def test_upload_firmware_model_not_found(
        self, client: FlaskClient
    ) -> None:
        """Test uploading firmware for non-existent model returns 404."""
        firmware_content = create_test_firmware(b"1.0.0")

        response = client.post(
            "/api/pipeline/models/nonexistent/firmware",
            data=firmware_content,
            content_type="application/octet-stream",
        )

        assert response.status_code == 404
        data = response.get_json()
        assert "nonexistent" in data["error"]

    def test_upload_firmware_publishes_mqtt_for_devices(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test that firmware upload publishes MQTT notifications for all devices."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="mqtttest", name="MQTT Test")

            # Create a device for this model
            keycloak_service = container.keycloak_admin_service()
            with patch.object(
                keycloak_service,
                "create_client",
                return_value=MagicMock(client_id="test", secret="test-secret"),
            ), patch.object(
                keycloak_service,
                "update_client_metadata",
            ):
                device_service = container.device_service()
                device = device_service.create_device(
                    device_model_id=model.id, config="{}"
                )
                expected_client_id = device.client_id

            container.db_session().commit()

        firmware_content = create_test_firmware(b"2.0.0")
        mqtt_service = app.container.mqtt_service()

        with patch.object(mqtt_service, "publish") as mock_publish:
            response = client.post(
                "/api/pipeline/models/mqtttest/firmware",
                data=firmware_content,
                content_type="application/octet-stream",
            )

            assert response.status_code == 200

            # Verify MQTT was published
            mock_publish.assert_called_once()
            call_args = mock_publish.call_args[0]
            topic = call_args[0]
            payload_str = call_args[1]

            assert topic == "iotsupport/updates/firmware"
            payload = json.loads(payload_str)
            assert payload["client_id"] == expected_client_id
            assert payload["firmware_version"] == "2.0.0"

    def test_upload_firmware_no_content_returns_400(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test uploading empty firmware returns 400."""
        with app.app_context():
            model_service = container.device_model_service()
            model_service.create_device_model(code="emptytest", name="Empty Test")
            container.db_session().commit()

        response = client.post(
            "/api/pipeline/models/emptytest/firmware",
            data=b"",
            content_type="application/octet-stream",
        )

        assert response.status_code == 400


class TestPipelineFirmwareZipUpload:
    """Tests for ZIP firmware upload via POST /api/pipeline/models/<code>/firmware."""

    def _create_test_zip(self, model_code: str, version: bytes) -> bytes:
        """Create a valid firmware ZIP for testing."""
        bin_content = create_test_firmware(version)
        version_json = json.dumps({
            "git_commit": "a1b2c3d4e5f6",
            "idf_version": "v5.2.1",
            "firmware_version": version.decode("utf-8"),
        }).encode("utf-8")

        buf = BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(f"{model_code}.bin", bin_content)
            zf.writestr(f"{model_code}.elf", b"\x7fELF" + b"\x00" * 100)
            zf.writestr(f"{model_code}.map", b"Memory Map\n")
            zf.writestr("sdkconfig", b"CONFIG_IDF_TARGET=\"esp32s3\"\n")
            zf.writestr("version.json", version_json)
        return buf.getvalue()

    def test_upload_firmware_zip_success(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test uploading firmware as a ZIP bundle via pipeline."""
        model_code = "ziptest"
        with app.app_context():
            model_service = container.device_model_service()
            model_service.create_device_model(code=model_code, name="ZIP Test")
            container.db_session().commit()

        zip_content = self._create_test_zip(model_code, b"3.0.0")

        response = client.post(
            f"/api/pipeline/models/{model_code}/firmware",
            data=zip_content,
            content_type="application/octet-stream",
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data["firmware_version"] == "3.0.0"
        assert data["code"] == model_code

    def test_upload_firmware_zip_invalid_structure(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test uploading ZIP with wrong structure returns 400."""
        model_code = "zipbad"
        with app.app_context():
            model_service = container.device_model_service()
            model_service.create_device_model(code=model_code, name="Bad ZIP Test")
            container.db_session().commit()

        # Create a ZIP missing required files
        buf = BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("random.txt", b"not firmware")
        bad_zip = buf.getvalue()

        response = client.post(
            f"/api/pipeline/models/{model_code}/firmware",
            data=bad_zip,
            content_type="application/octet-stream",
        )

        assert response.status_code == 400

    def test_upload_firmware_zip_creates_versioned_file(
        self, app: Flask, client: FlaskClient, container: ServiceContainer, test_settings: Settings
    ) -> None:
        """Test that ZIP upload creates versioned ZIP on disk."""
        model_code = "zipfile"
        with app.app_context():
            model_service = container.device_model_service()
            model_service.create_device_model(code=model_code, name="ZIP File Test")
            container.db_session().commit()

        zip_content = self._create_test_zip(model_code, b"4.1.0")

        response = client.post(
            f"/api/pipeline/models/{model_code}/firmware",
            data=zip_content,
            content_type="application/octet-stream",
        )

        assert response.status_code == 200

        # Verify versioned ZIP exists on disk
        assets_dir = test_settings.assets_dir
        assert assets_dir is not None
        zip_path = assets_dir / model_code / "firmware-4.1.0.zip"
        assert zip_path.exists()

        # Verify legacy .bin also exists
        legacy_path = assets_dir / f"firmware-{model_code}.bin"
        assert legacy_path.exists()

    def test_upload_plain_bin_still_works(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test that plain .bin upload still works alongside ZIP support."""
        model_code = "bincompat"
        with app.app_context():
            model_service = container.device_model_service()
            model_service.create_device_model(code=model_code, name="Binary Compat Test")
            container.db_session().commit()

        firmware_content = create_test_firmware(b"1.0.0")

        response = client.post(
            f"/api/pipeline/models/{model_code}/firmware",
            data=firmware_content,
            content_type="application/octet-stream",
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data["firmware_version"] == "1.0.0"


class TestPipelineFirmwareVersion:
    """Tests for GET /api/pipeline/models/<code>/firmware-version."""

    def test_get_firmware_version_success(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test getting firmware version by model code."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="vertest", name="Version Test")
            model.firmware_version = "3.2.1"
            container.db_session().commit()

        response = client.get("/api/pipeline/models/vertest/firmware-version")

        assert response.status_code == 200
        data = response.get_json()
        assert data["code"] == "vertest"
        assert data["firmware_version"] == "3.2.1"

    def test_get_firmware_version_no_firmware(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test getting firmware version when none uploaded."""
        with app.app_context():
            model_service = container.device_model_service()
            model_service.create_device_model(code="nofwtest", name="No Firmware Test")
            container.db_session().commit()

        response = client.get("/api/pipeline/models/nofwtest/firmware-version")

        assert response.status_code == 200
        data = response.get_json()
        assert data["code"] == "nofwtest"
        assert data["firmware_version"] is None

    def test_get_firmware_version_model_not_found(
        self, client: FlaskClient
    ) -> None:
        """Test getting firmware version for non-existent model returns 404."""
        response = client.get("/api/pipeline/models/nonexistent/firmware-version")

        assert response.status_code == 404
        data = response.get_json()
        assert "nonexistent" in data["error"]


class TestPipelineUploadScript:
    """Tests for GET /api/pipeline/upload.sh."""

    def test_get_upload_script_returns_shell_script(
        self, app: Flask, client: FlaskClient
    ) -> None:
        """Test that upload script endpoint returns a valid shell script."""
        response = client.get("/api/pipeline/upload.sh")

        assert response.status_code == 200
        assert response.content_type == "text/x-shellscript; charset=utf-8"

        script = response.data.decode("utf-8")
        assert script.startswith("#!/bin/sh")
        assert "IOTSUPPORT_CLIENT_ID" in script
        assert "IOTSUPPORT_CLIENT_SECRET" in script

    def test_get_upload_script_contains_backend_url(
        self, app: Flask, client: FlaskClient
    ) -> None:
        """Test that the script contains the inferred backend URL."""
        response = client.get("/api/pipeline/upload.sh")

        script = response.data.decode("utf-8")
        # Flask test client uses localhost by default
        assert 'BACKEND_URL="http://localhost"' in script

    def test_get_upload_script_contains_token_url(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test that the script contains the token URL from config."""
        # Get the configured token URL
        config: Settings = container.config()
        expected_token_url = config.oidc_token_url or ""

        response = client.get("/api/pipeline/upload.sh")

        script = response.data.decode("utf-8")
        assert f'TOKEN_URL="{expected_token_url}"' in script

    def test_get_upload_script_respects_forwarded_headers(
        self, app: Flask, client: FlaskClient
    ) -> None:
        """Test that the script uses X-Forwarded-* headers when present."""
        response = client.get(
            "/api/pipeline/upload.sh",
            headers={
                "X-Forwarded-Proto": "https",
                "X-Forwarded-Host": "iotsupport.example.com",
            },
        )

        script = response.data.decode("utf-8")
        assert 'BACKEND_URL="https://iotsupport.example.com"' in script

    def test_get_upload_script_is_public(
        self, app: Flask, client: FlaskClient
    ) -> None:
        """Test that upload script endpoint is accessible without authentication."""
        # This test verifies the @public decorator works
        # The client fixture doesn't set up auth, so if this returns 200
        # it means the endpoint is correctly marked as public
        response = client.get("/api/pipeline/upload.sh")
        assert response.status_code == 200

    def test_get_upload_script_contains_usage_instructions(
        self, app: Flask, client: FlaskClient
    ) -> None:
        """Test that the script contains usage instructions."""
        response = client.get("/api/pipeline/upload.sh")

        script = response.data.decode("utf-8")
        assert "Usage:" in script
        assert "model_code" in script
        assert "firmware.bin" in script

    def test_get_upload_script_contains_auto_detect_logic(
        self, app: Flask, client: FlaskClient
    ) -> None:
        """Test that the script contains auto-detection from project_description.json."""
        response = client.get("/api/pipeline/upload.sh")

        script = response.data.decode("utf-8")
        assert "project_description.json" in script
        assert "project_name" in script
        assert "Auto-detected" in script

    def test_get_upload_script_contains_zip_packaging(
        self, app: Flask, client: FlaskClient
    ) -> None:
        """Test that the shell script contains ZIP packaging logic."""
        response = client.get("/api/pipeline/upload.sh")

        script = response.data.decode("utf-8")
        assert "version.json" in script
        assert "zip" in script.lower()
        assert "sdkconfig" in script
        assert ".elf" in script
        assert ".map" in script


class TestPipelineUploadScriptPowerShell:
    """Tests for GET /api/pipeline/upload.ps1."""

    def test_get_upload_script_returns_powershell_script(
        self, app: Flask, client: FlaskClient
    ) -> None:
        """Test that upload script endpoint returns a valid PowerShell script."""
        response = client.get("/api/pipeline/upload.ps1")

        assert response.status_code == 200
        assert response.content_type == "text/plain; charset=utf-8"

        script = response.data.decode("utf-8")
        assert "function Upload-Firmware" in script
        assert "IOTSUPPORT_CLIENT_ID" in script
        assert "IOTSUPPORT_CLIENT_SECRET" in script

    def test_get_upload_script_contains_backend_url(
        self, app: Flask, client: FlaskClient
    ) -> None:
        """Test that the script contains the inferred backend URL."""
        response = client.get("/api/pipeline/upload.ps1")

        script = response.data.decode("utf-8")
        # Flask test client uses localhost by default
        assert '$BackendUrl = "http://localhost"' in script

    def test_get_upload_script_contains_token_url(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test that the script contains the token URL from config."""
        config: Settings = container.config()
        expected_token_url = config.oidc_token_url or ""

        response = client.get("/api/pipeline/upload.ps1")

        script = response.data.decode("utf-8")
        assert f'$TokenUrl = "{expected_token_url}"' in script

    def test_get_upload_script_respects_forwarded_headers(
        self, app: Flask, client: FlaskClient
    ) -> None:
        """Test that the script uses X-Forwarded-* headers when present."""
        response = client.get(
            "/api/pipeline/upload.ps1",
            headers={
                "X-Forwarded-Proto": "https",
                "X-Forwarded-Host": "iotsupport.example.com",
            },
        )

        script = response.data.decode("utf-8")
        assert '$BackendUrl = "https://iotsupport.example.com"' in script

    def test_get_upload_script_is_public(
        self, app: Flask, client: FlaskClient
    ) -> None:
        """Test that upload script endpoint is accessible without authentication."""
        response = client.get("/api/pipeline/upload.ps1")
        assert response.status_code == 200

    def test_get_upload_script_contains_usage_instructions(
        self, app: Flask, client: FlaskClient
    ) -> None:
        """Test that the script contains usage instructions."""
        response = client.get("/api/pipeline/upload.ps1")

        script = response.data.decode("utf-8")
        assert "Usage:" in script
        assert "model_code" in script
        assert "firmware.bin" in script

    def test_get_upload_script_contains_auto_detect_logic(
        self, app: Flask, client: FlaskClient
    ) -> None:
        """Test that the script contains auto-detection from project_description.json."""
        response = client.get("/api/pipeline/upload.ps1")

        script = response.data.decode("utf-8")
        assert "project_description.json" in script
        assert "project_name" in script
        assert "Auto-detected" in script

    def test_get_upload_script_contains_zip_packaging(
        self, app: Flask, client: FlaskClient
    ) -> None:
        """Test that the PowerShell script contains ZIP packaging logic."""
        response = client.get("/api/pipeline/upload.ps1")

        script = response.data.decode("utf-8")
        assert "version.json" in script
        assert "Compress-Archive" in script
        assert "sdkconfig" in script
        assert ".elf" in script
        assert ".map" in script
