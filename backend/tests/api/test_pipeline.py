"""Tests for pipeline API endpoints."""

import json
import struct
from unittest.mock import MagicMock, patch

from flask import Flask
from flask.testing import FlaskClient

from app.services.container import ServiceContainer


class TestPipelineFirmwareUpload:
    """Tests for POST /api/pipeline/models/<code>/firmware."""

    @staticmethod
    def _create_test_firmware(version: bytes) -> bytes:
        """Create a test firmware binary with valid ESP32 AppInfo header."""
        # ESP32 image header (24 bytes)
        image_header = bytes(24)

        # Segment header (8 bytes)
        segment_header = bytes(8)

        # AppInfo structure (256 bytes)
        magic = struct.pack("<I", 0xABCD5432)  # Magic word
        secure_version = struct.pack("<I", 0)
        reserved1 = bytes(8)
        version_field = version.ljust(32, b"\x00")[:32]
        project_name = b"test_project".ljust(32, b"\x00")
        compile_time = b"12:00:00".ljust(16, b"\x00")
        compile_date = b"Jan 01 2024".ljust(16, b"\x00")
        idf_version = b"v5.0".ljust(32, b"\x00")
        app_elf_sha256 = bytes(32)
        reserved_rest = bytes(256 - 4 - 4 - 8 - 32 - 32 - 16 - 16 - 32 - 32)

        app_info = (
            magic + secure_version + reserved1 + version_field +
            project_name + compile_time + compile_date + idf_version +
            app_elf_sha256 + reserved_rest
        )

        return image_header + segment_header + app_info

    def test_upload_firmware_by_code_success(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test uploading firmware using model code."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="pipetest", name="Pipeline Test")
            container.db_session().commit()

        firmware_content = self._create_test_firmware(b"1.0.0")

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
        firmware_content = self._create_test_firmware(b"1.0.0")

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

        firmware_content = self._create_test_firmware(b"2.0.0")
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
