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
        """Test triggering fleet-wide rotation broadcasts rotation nudge."""
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

        rns = container.rotation_nudge_service()
        with patch.object(rns, "broadcast", return_value=True) as mock_nudge:
            response = client.post("/api/rotation/trigger")

            assert response.status_code == 200
            data = response.get_json()
            assert data["queued_count"] == 2

            # Verify rotation nudge was broadcast
            mock_nudge.assert_called_once_with(source="web")

    def test_trigger_fleet_rotation_no_ok_devices(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test fleet rotation when no devices in OK state still broadcasts nudge."""
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

        rns = container.rotation_nudge_service()
        with patch.object(rns, "broadcast", return_value=False) as mock_nudge:
            response = client.post("/api/rotation/trigger")

            assert response.status_code == 200
            data = response.get_json()
            assert data["queued_count"] == 0

            # Nudge is still broadcast even when no devices were queued
            mock_nudge.assert_called_once_with(source="web")

    def test_trigger_fleet_rotation_no_devices(
        self, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test fleet rotation when no devices exist still broadcasts nudge."""
        rns = container.rotation_nudge_service()
        with patch.object(rns, "broadcast", return_value=False) as mock_nudge:
            response = client.post("/api/rotation/trigger")

            assert response.status_code == 200
            data = response.get_json()
            assert data["queued_count"] == 0

            mock_nudge.assert_called_once_with(source="web")


class TestRotationStatusActiveFlag:
    """Tests for inactive count in rotation status endpoint."""

    def test_rotation_status_includes_inactive_count(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test that GET /rotation/status includes inactive field."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="statact1", name="Status Active Test")

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
                # 2 active devices
                device_service.create_device(device_model_id=model.id, config="{}")
                device_service.create_device(device_model_id=model.id, config="{}")

                # 1 inactive device
                d3 = device_service.create_device(device_model_id=model.id, config="{}")
                d3.active = False

        response = client.get("/api/rotation/status")

        assert response.status_code == 200
        data = response.get_json()
        assert data["inactive"] == 1
        # counts_by_state still includes all devices
        assert data["counts_by_state"]["OK"] == 3

    def test_rotation_status_no_inactive(self, client: FlaskClient) -> None:
        """Test that inactive count is 0 when no devices exist."""
        response = client.get("/api/rotation/status")

        assert response.status_code == 200
        data = response.get_json()
        assert data["inactive"] == 0


class TestRotationDashboardActiveFlag:
    """Tests for inactive group in dashboard endpoint."""

    def test_dashboard_includes_inactive_group(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test that GET /rotation/dashboard includes inactive list and count."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="dashact1", name="Dashboard Active Test")

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

                # Active OK device
                device_service.create_device(device_model_id=model.id, config="{}")

                # Inactive device
                d2 = device_service.create_device(device_model_id=model.id, config="{}")
                d2.active = False

        response = client.get("/api/rotation/dashboard")

        assert response.status_code == 200
        data = response.get_json()
        assert data["counts"]["healthy"] == 1
        assert data["counts"]["inactive"] == 1
        assert len(data["inactive"]) == 1
        assert data["inactive"][0]["active"] is False

    def test_dashboard_empty_inactive_group(self, client: FlaskClient) -> None:
        """Test dashboard with no devices shows empty inactive list."""
        response = client.get("/api/rotation/dashboard")

        assert response.status_code == 200
        data = response.get_json()
        assert data["inactive"] == []
        assert data["counts"]["inactive"] == 0

    def test_fleet_trigger_skips_inactive_devices(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test that POST /rotation/trigger skips inactive devices."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="trgact1", name="Trigger Active Test")

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

                # 2 active OK devices
                device_service.create_device(device_model_id=model.id, config="{}")
                device_service.create_device(device_model_id=model.id, config="{}")

                # 1 inactive OK device
                d3 = device_service.create_device(device_model_id=model.id, config="{}")
                d3.active = False

        rns = container.rotation_nudge_service()
        with patch.object(rns, "broadcast", return_value=True):
            response = client.post("/api/rotation/trigger")

            assert response.status_code == 200
            data = response.get_json()
            # Only 2 active devices should be queued
            assert data["queued_count"] == 2
