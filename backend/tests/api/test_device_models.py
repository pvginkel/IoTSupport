"""Tests for device models API endpoints."""

import json
from unittest.mock import MagicMock, patch

from flask import Flask
from flask.testing import FlaskClient

from app.services.container import ServiceContainer
from tests.conftest import create_test_firmware
from tests.services.test_firmware_service import _create_test_zip


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

    def test_upload_firmware_zip_success(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test uploading firmware as ZIP creates S3 objects and returns version."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="fw_zip", name="FW ZIP Test")
            model_id = model.id

        zip_content = _create_test_zip("fw_zip", b"1.2.3")

        response = client.post(
            f"/api/device-models/{model_id}/firmware",
            data=zip_content,
            content_type="application/octet-stream",
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data["firmware_version"] == "1.2.3"

        # Verify S3 objects exist
        s3 = container.s3_service()
        assert s3.file_exists("firmware/fw_zip/1.2.3/firmware.bin")
        assert s3.file_exists("firmware/fw_zip/1.2.3/firmware.elf")

    def test_upload_firmware_raw_bin_rejected(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test that raw .bin upload is rejected (only ZIP accepted)."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="fw_raw", name="FW Raw Test")
            model_id = model.id

        firmware_content = create_test_firmware(b"1.0.0")

        response = client.post(
            f"/api/device-models/{model_id}/firmware",
            data=firmware_content,
            content_type="application/octet-stream",
        )

        assert response.status_code == 400

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

        # Upload firmware as ZIP and verify MQTT publish
        zip_content = _create_test_zip("fw_mqtt", b"1.2.3")
        mqtt_service = app.container.mqtt_service()

        with patch.object(mqtt_service, "publish") as mock_publish:
            response = client.post(
                f"/api/device-models/{model_id}/firmware",
                data=zip_content,
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

        zip_content = _create_test_zip("fw_no_dev", b"2.0.0")
        mqtt_service = app.container.mqtt_service()

        with patch.object(mqtt_service, "publish") as mock_publish:
            response = client.post(
                f"/api/device-models/{model_id}/firmware",
                data=zip_content,
                content_type="application/octet-stream",
            )

            assert response.status_code == 200
            mock_publish.assert_not_called()


class TestDeviceModelsFirmwareDownload:
    """Tests for GET /api/device-models/<id>/firmware."""

    def test_download_firmware_success(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test downloading firmware .bin from S3."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="fw_dl", name="FW Download")
            model_id = model.id

            # Upload firmware via service
            zip_content = _create_test_zip("fw_dl", b"3.0.0")
            model_service.upload_firmware(model_id, zip_content)

        response = client.get(f"/api/device-models/{model_id}/firmware")

        assert response.status_code == 200
        assert response.content_type == "application/octet-stream"
        # Verify the downloaded data is valid firmware
        assert len(response.data) > 0

    def test_download_firmware_not_uploaded(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test downloading firmware when none uploaded returns 404."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="fw_nodl", name="No FW")
            model_id = model.id

        response = client.get(f"/api/device-models/{model_id}/firmware")

        assert response.status_code == 404
