"""Tests for devices API endpoints."""

from unittest.mock import MagicMock, patch

from flask import Flask
from flask.testing import FlaskClient

from app.models.device import RotationState
from app.services.container import ServiceContainer


class TestDevicesList:
    """Tests for GET /api/devices."""

    def test_list_devices_empty(self, client: FlaskClient) -> None:
        """Test listing when no devices exist."""
        response = client.get("/api/devices")

        assert response.status_code == 200
        data = response.get_json()
        assert data["devices"] == []

    def test_list_devices_returns_all(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test that list returns all devices."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="list1", name="List Test")

            keycloak_service = container.keycloak_admin_service()
            with patch.object(
                keycloak_service,
                "create_client",
                return_value=MagicMock(client_id="test", secret="test-secret"),
            ):
                device_service = container.device_service()
                device_service.create_device(device_model_id=model.id, config="{}")
                device_service.create_device(device_model_id=model.id, config="{}")

        response = client.get("/api/devices")

        assert response.status_code == 200
        data = response.get_json()
        assert len(data["devices"]) == 2

    def test_list_devices_filter_by_model(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test filtering devices by model ID."""
        with app.app_context():
            model_service = container.device_model_service()
            model1 = model_service.create_device_model(code="filt1", name="Filter One")
            model2 = model_service.create_device_model(code="filt2", name="Filter Two")

            keycloak_service = container.keycloak_admin_service()
            with patch.object(
                keycloak_service,
                "create_client",
                return_value=MagicMock(client_id="test", secret="test-secret"),
            ):
                device_service = container.device_service()
                device_service.create_device(device_model_id=model1.id, config="{}")
                device_service.create_device(device_model_id=model2.id, config="{}")
                model_id = model1.id

        response = client.get(f"/api/devices?model_id={model_id}")

        assert response.status_code == 200
        data = response.get_json()
        assert len(data["devices"]) == 1


class TestDevicesCreate:
    """Tests for POST /api/devices."""

    def test_create_device_success(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test creating a device."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="create1", name="Create Test")
            model_id = model.id

        with patch.object(
            container.keycloak_admin_service(),
            "create_client",
            return_value=MagicMock(client_id="test", secret="test-secret"),
        ):
            response = client.post(
                "/api/devices",
                json={
                    "device_model_id": model_id,
                    "config": '{"setting": "value"}',
                },
            )

        assert response.status_code == 201
        data = response.get_json()
        assert data["device_model_id"] == model_id
        assert len(data["key"]) == 8
        # Config is returned as parsed dict in response schema
        assert data["config"] == {"setting": "value"}

    def test_create_device_invalid_model_id(self, client: FlaskClient) -> None:
        """Test creating device with invalid model ID returns 404."""
        response = client.post(
            "/api/devices",
            json={
                "device_model_id": 99999,
                "config": "{}",
            },
        )

        assert response.status_code == 404

    def test_create_device_invalid_json_config(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test creating device with invalid JSON config returns 400."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="create2", name="Create Test 2")
            model_id = model.id

        response = client.post(
            "/api/devices",
            json={
                "device_model_id": model_id,
                "config": "not valid json",
            },
        )

        assert response.status_code == 400


class TestDevicesGet:
    """Tests for GET /api/devices/<id>."""

    def test_get_device_success(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test getting a device by ID."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="get1", name="Get Test")

            keycloak_service = container.keycloak_admin_service()
            with patch.object(
                keycloak_service,
                "create_client",
                return_value=MagicMock(client_id="test", secret="test-secret"),
            ):
                device_service = container.device_service()
                device = device_service.create_device(device_model_id=model.id, config="{}")
                device_id = device.id
                device_key = device.key

        response = client.get(f"/api/devices/{device_id}")

        assert response.status_code == 200
        data = response.get_json()
        assert data["key"] == device_key

    def test_get_device_not_found(self, client: FlaskClient) -> None:
        """Test getting a nonexistent device returns 404."""
        response = client.get("/api/devices/99999")

        assert response.status_code == 404


class TestDevicesUpdate:
    """Tests for PUT /api/devices/<id>."""

    def test_update_device_config_success(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test updating a device's configuration."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="upd1", name="Update Test")

            keycloak_service = container.keycloak_admin_service()
            with patch.object(
                keycloak_service,
                "create_client",
                return_value=MagicMock(client_id="test", secret="test-secret"),
            ):
                device_service = container.device_service()
                device = device_service.create_device(
                    device_model_id=model.id, config='{"old": "value"}'
                )
                device_id = device.id

        response = client.put(
            f"/api/devices/{device_id}",
            json={"config": '{"new": "value"}'},
        )

        assert response.status_code == 200
        data = response.get_json()
        # Config is returned as parsed dict in response schema
        assert data["config"] == {"new": "value"}

    def test_update_device_not_found(self, client: FlaskClient) -> None:
        """Test updating a nonexistent device returns 404."""
        response = client.put(
            "/api/devices/99999",
            json={"config": "{}"},
        )

        assert response.status_code == 404


class TestDevicesDelete:
    """Tests for DELETE /api/devices/<id>."""

    def test_delete_device_success(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test deleting a device."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="del1", name="Delete Test")

            keycloak_service = container.keycloak_admin_service()
            with patch.object(
                keycloak_service,
                "create_client",
                return_value=MagicMock(client_id="test", secret="test-secret"),
            ):
                device_service = container.device_service()
                device = device_service.create_device(device_model_id=model.id, config="{}")
                device_id = device.id

        with patch.object(container.keycloak_admin_service(), "delete_client"):
            response = client.delete(f"/api/devices/{device_id}")

        assert response.status_code == 204

        # Verify it's gone
        response = client.get(f"/api/devices/{device_id}")
        assert response.status_code == 404

    def test_delete_device_not_found(self, client: FlaskClient) -> None:
        """Test deleting a nonexistent device returns 404."""
        response = client.delete("/api/devices/99999")

        assert response.status_code == 404


class TestDevicesProvisioning:
    """Tests for GET /api/devices/<id>/provisioning."""

    def test_get_provisioning_package_success(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test getting provisioning package for a device."""
        import json

        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="prov1", name="Provisioning Test")

            keycloak_service = container.keycloak_admin_service()
            with patch.object(
                keycloak_service,
                "create_client",
                return_value=MagicMock(client_id="test", secret="test-secret"),
            ):
                device_service = container.device_service()
                device = device_service.create_device(device_model_id=model.id, config="{}")
                device_id = device.id
                device_key = device.key

        with patch.object(
            container.keycloak_admin_service(), "get_client_secret", return_value="secret123"
        ):
            response = client.get(f"/api/devices/{device_id}/provisioning")

        assert response.status_code == 200
        # Response is a binary download, parse the JSON content
        data = json.loads(response.data)
        assert data["device_key"] == device_key
        assert data["client_secret"] == "secret123"
        assert "client_id" in data

    def test_get_provisioning_not_found(self, client: FlaskClient) -> None:
        """Test getting provisioning for nonexistent device returns 404."""
        response = client.get("/api/devices/99999/provisioning")

        assert response.status_code == 404


class TestDevicesRotate:
    """Tests for POST /api/devices/<id>/rotate."""

    def test_trigger_rotation_success(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test triggering rotation for a device."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="rot1", name="Rotation Test")

            keycloak_service = container.keycloak_admin_service()
            with patch.object(
                keycloak_service,
                "create_client",
                return_value=MagicMock(client_id="test", secret="test-secret"),
            ):
                device_service = container.device_service()
                device = device_service.create_device(device_model_id=model.id, config="{}")
                device_id = device.id

        response = client.post(f"/api/devices/{device_id}/rotate")

        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "queued"

    def test_trigger_rotation_already_pending(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test triggering rotation when already pending."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="rot2", name="Rotation Test 2")

            keycloak_service = container.keycloak_admin_service()
            with patch.object(
                keycloak_service,
                "create_client",
                return_value=MagicMock(client_id="test", secret="test-secret"),
            ):
                device_service = container.device_service()
                device = device_service.create_device(device_model_id=model.id, config="{}")
                device.rotation_state = RotationState.PENDING.value
                device_id = device.id

        response = client.post(f"/api/devices/{device_id}/rotate")

        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "already_pending"

    def test_trigger_rotation_not_found(self, client: FlaskClient) -> None:
        """Test triggering rotation for nonexistent device returns 404."""
        response = client.post("/api/devices/99999/rotate")

        assert response.status_code == 404
