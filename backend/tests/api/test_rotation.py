"""Tests for rotation API endpoints."""

from unittest.mock import MagicMock, patch

from flask import Flask
from flask.testing import FlaskClient

from app.models.device import RotationState
from app.services.container import ServiceContainer


class TestRotationStatus:
    """Tests for GET /api/rotation/status."""

    def test_get_rotation_status_no_devices(self, client: FlaskClient) -> None:
        """Test getting status when no devices exist."""
        response = client.get("/api/rotation/status")

        assert response.status_code == 200
        data = response.get_json()
        assert data["counts_by_state"]["OK"] == 0
        assert data["counts_by_state"]["QUEUED"] == 0
        assert data["counts_by_state"]["PENDING"] == 0
        assert data["counts_by_state"]["TIMEOUT"] == 0
        assert data["pending_device_id"] is None

    def test_get_rotation_status_with_devices(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test getting status with devices."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="status1", name="Status Test")

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
                d1 = device_service.create_device(device_model_id=model.id, config="{}")
                d2 = device_service.create_device(device_model_id=model.id, config="{}")

                d1.rotation_state = RotationState.OK.value
                d2.rotation_state = RotationState.QUEUED.value

        response = client.get("/api/rotation/status")

        assert response.status_code == 200
        data = response.get_json()
        assert data["counts_by_state"]["OK"] == 1
        assert data["counts_by_state"]["QUEUED"] == 1


class TestRotationTriggerFleet:
    """Tests for POST /api/rotation/trigger."""

    def test_trigger_fleet_rotation(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test triggering fleet-wide rotation."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="fleet1", name="Fleet Test")

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
                device_service.create_device(device_model_id=model.id, config="{}")
                device_service.create_device(device_model_id=model.id, config="{}")

        response = client.post("/api/rotation/trigger")

        assert response.status_code == 200
        data = response.get_json()
        assert data["queued_count"] == 2

    def test_trigger_fleet_rotation_no_ok_devices(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test fleet rotation when no devices in OK state."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="fleet2", name="Fleet Test 2")

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
                device = device_service.create_device(device_model_id=model.id, config="{}")
                device.rotation_state = RotationState.PENDING.value

        response = client.post("/api/rotation/trigger")

        assert response.status_code == 200
        data = response.get_json()
        assert data["queued_count"] == 0

    def test_trigger_fleet_rotation_no_devices(self, client: FlaskClient) -> None:
        """Test fleet rotation when no devices exist."""
        response = client.post("/api/rotation/trigger")

        assert response.status_code == 200
        data = response.get_json()
        assert data["queued_count"] == 0
