"""Tests for device models API endpoints."""

import json
import struct
from unittest.mock import MagicMock, patch

from flask import Flask
from flask.testing import FlaskClient

from app.services.container import ServiceContainer


class TestDeviceModelsList:
    """Tests for GET /api/device-models."""

    def test_list_device_models_empty(self, client: FlaskClient) -> None:
        """Test listing when no device models exist."""
        response = client.get("/api/device-models")

        assert response.status_code == 200
        data = response.get_json()
        assert data["device_models"] == []

    def test_list_device_models_returns_all(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test that list returns all device models."""
        with app.app_context():
            service = container.device_model_service()
            service.create_device_model(code="model1", name="Model One")
            service.create_device_model(code="model2", name="Model Two")

        response = client.get("/api/device-models")

        assert response.status_code == 200
        data = response.get_json()
        assert len(data["device_models"]) == 2


class TestDeviceModelsCreate:
    """Tests for POST /api/device-models."""

    def test_create_device_model_success(self, client: FlaskClient) -> None:
        """Test creating a device model."""
        response = client.post(
            "/api/device-models",
            json={"code": "sensor", "name": "Temperature Sensor"},
        )

        assert response.status_code == 201
        data = response.get_json()
        assert data["code"] == "sensor"
        assert data["name"] == "Temperature Sensor"
        assert data["id"] is not None

    def test_create_device_model_duplicate_code(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test that duplicate code returns 409 CONFLICT."""
        with app.app_context():
            service = container.device_model_service()
            service.create_device_model(code="dup", name="Existing")

        response = client.post(
            "/api/device-models",
            json={"code": "dup", "name": "Duplicate"},
        )

        assert response.status_code == 409
        data = response.get_json()
        assert "already exists" in data["error"]

    def test_create_device_model_invalid_code(self, client: FlaskClient) -> None:
        """Test that invalid code returns 400."""
        response = client.post(
            "/api/device-models",
            json={"code": "Invalid-Code", "name": "Test"},
        )

        assert response.status_code == 400

    def test_create_device_model_missing_fields(self, client: FlaskClient) -> None:
        """Test that missing required fields returns 400 or 422."""
        response = client.post("/api/device-models", json={})

        assert response.status_code in [400, 422]


class TestDeviceModelsGet:
    """Tests for GET /api/device-models/<id>."""

    def test_get_device_model_success(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test getting a device model by ID."""
        with app.app_context():
            service = container.device_model_service()
            model = service.create_device_model(code="get1", name="Get Test")
            model_id = model.id

        response = client.get(f"/api/device-models/{model_id}")

        assert response.status_code == 200
        data = response.get_json()
        assert data["code"] == "get1"
        assert data["name"] == "Get Test"

    def test_get_device_model_not_found(self, client: FlaskClient) -> None:
        """Test getting a nonexistent device model returns 404."""
        response = client.get("/api/device-models/99999")

        assert response.status_code == 404


class TestDeviceModelsUpdate:
    """Tests for PUT /api/device-models/<id>."""

    def test_update_device_model_success(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test updating a device model."""
        with app.app_context():
            service = container.device_model_service()
            model = service.create_device_model(code="upd1", name="Original")
            model_id = model.id

        response = client.put(
            f"/api/device-models/{model_id}",
            json={"name": "Updated Name"},
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data["name"] == "Updated Name"

    def test_update_device_model_not_found(self, client: FlaskClient) -> None:
        """Test updating a nonexistent device model returns 404."""
        response = client.put(
            "/api/device-models/99999",
            json={"name": "Updated"},
        )

        assert response.status_code == 404


class TestDeviceModelsDelete:
    """Tests for DELETE /api/device-models/<id>."""

    def test_delete_device_model_success(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test deleting a device model."""
        with app.app_context():
            service = container.device_model_service()
            model = service.create_device_model(code="del1", name="To Delete")
            model_id = model.id

        response = client.delete(f"/api/device-models/{model_id}")

        assert response.status_code == 204

        # Verify it's gone
        response = client.get(f"/api/device-models/{model_id}")
        assert response.status_code == 404

    def test_delete_device_model_not_found(self, client: FlaskClient) -> None:
        """Test deleting a nonexistent device model returns 404."""
        response = client.delete("/api/device-models/99999")

        assert response.status_code == 404


class TestDeviceModelsFirmwareUpload:
    """Tests for POST /api/device-models/<id>/firmware."""

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

    def test_upload_firmware_publishes_mqtt_for_each_device(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test that firmware upload publishes MQTT notification for each device."""
        with app.app_context():
            # Create device model
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="fw_mqtt", name="FW MQTT Test")
            model_id = model.id

            # Create two devices for this model
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
                device1 = device_service.create_device(device_model_id=model_id, config="{}")
                device2 = device_service.create_device(device_model_id=model_id, config="{}")
                device1_client_id = device1.client_id
                device2_client_id = device2.client_id

            # Commit the session so devices are persisted for the firmware upload request
            container.db_session().commit()

        # Upload firmware and verify MQTT publish
        firmware_content = self._create_test_firmware(b"1.2.3")
        mqtt_service = app.container.mqtt_service()

        with patch.object(mqtt_service, "publish") as mock_publish:
            response = client.post(
                f"/api/device-models/{model_id}/firmware",
                data=firmware_content,
                content_type="application/octet-stream",
            )

            assert response.status_code == 200
            data = response.get_json()
            assert data["firmware_version"] == "1.2.3"

            # Verify MQTT was published for each device
            assert mock_publish.call_count == 2

            # Extract published payloads
            published_payloads = [
                json.loads(call[0][1]) for call in mock_publish.call_args_list
            ]
            published_client_ids = {p["client_id"] for p in published_payloads}

            assert device1_client_id in published_client_ids
            assert device2_client_id in published_client_ids

            # Verify topic and payload format
            for call in mock_publish.call_args_list:
                topic, payload_str = call[0]
                assert topic == "iotsupport/updates/firmware"
                payload = json.loads(payload_str)
                assert "client_id" in payload
                assert payload["firmware_version"] == "1.2.3"

    def test_upload_firmware_no_devices_no_mqtt(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test that firmware upload with no devices doesn't publish MQTT."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="fw_no_dev", name="No Devices")
            model_id = model.id

        firmware_content = self._create_test_firmware(b"2.0.0")
        mqtt_service = app.container.mqtt_service()

        with patch.object(mqtt_service, "publish") as mock_publish:
            response = client.post(
                f"/api/device-models/{model_id}/firmware",
                data=firmware_content,
                content_type="application/octet-stream",
            )

            assert response.status_code == 200
            mock_publish.assert_not_called()
