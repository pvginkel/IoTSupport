"""Tests for device log stream subscribe/unsubscribe API endpoints."""

from unittest.mock import MagicMock, patch

from flask import Flask
from flask.testing import FlaskClient

from app.services.container import ServiceContainer


def _setup_device(
    app: Flask, container: ServiceContainer, entity_id: str | None = "sensor.living_room"
) -> int:
    """Create a device model and device with an entity_id for testing.

    Returns the device id.
    """
    with app.app_context():
        model_service = container.device_model_service()
        model = model_service.create_device_model(code="logstest", name="Log Stream Test")

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
            config_str = '{"deviceEntityId": "sensor.living_room"}' if entity_id else '{}'
            device = device_service.create_device(
                device_model_id=model.id, config=config_str
            )
            # Manually set entity_id (normally extracted from config by service)
            if entity_id:
                device.device_entity_id = entity_id

            return device.id


class TestDeviceLogSubscribe:
    """Tests for POST /api/device-logs/subscribe."""

    def test_subscribe_success(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Given a valid request_id with identity binding and valid device_id,
        when POST subscribe, then 200 with device_entity_id."""
        device_id = _setup_device(app, container)

        # Bind identity first (simulating SSE connect)
        dls = container.device_log_stream_service()
        dls.bind_identity("req-test-1", {})

        response = client.post(
            "/api/device-logs/subscribe",
            json={"request_id": "req-test-1", "device_id": device_id},
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "subscribed"
        assert data["device_entity_id"] == "sensor.living_room"

    def test_subscribe_device_not_found(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Given a device_id that doesn't exist, when POST subscribe, then 404."""
        dls = container.device_log_stream_service()
        dls.bind_identity("req-test-1", {})

        response = client.post(
            "/api/device-logs/subscribe",
            json={"request_id": "req-test-1", "device_id": 99999},
        )

        assert response.status_code == 404

    def test_subscribe_device_no_entity_id(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Given a device with no entity_id, when POST subscribe, then 404."""
        device_id = _setup_device(app, container, entity_id=None)

        dls = container.device_log_stream_service()
        dls.bind_identity("req-test-1", {})

        response = client.post(
            "/api/device-logs/subscribe",
            json={"request_id": "req-test-1", "device_id": device_id},
        )

        assert response.status_code == 404

    def test_subscribe_no_identity_binding(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Given request_id with no identity binding, when POST subscribe, then 403."""
        device_id = _setup_device(app, container)

        response = client.post(
            "/api/device-logs/subscribe",
            json={"request_id": "req-no-identity", "device_id": device_id},
        )

        assert response.status_code == 403

    def test_subscribe_missing_request_id(self, client: FlaskClient) -> None:
        """Given missing request_id in body, when POST subscribe, then 400."""
        response = client.post(
            "/api/device-logs/subscribe",
            json={"device_id": 1},
        )

        assert response.status_code == 400

    def test_subscribe_missing_device_id(self, client: FlaskClient) -> None:
        """Given missing device_id in body, when POST subscribe, then 400."""
        response = client.post(
            "/api/device-logs/subscribe",
            json={"request_id": "req-1"},
        )

        assert response.status_code == 400

    def test_subscribe_idempotent(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Subscribing same pair twice returns 200 both times."""
        device_id = _setup_device(app, container)

        dls = container.device_log_stream_service()
        dls.bind_identity("req-test-1", {})

        payload = {"request_id": "req-test-1", "device_id": device_id}
        response1 = client.post("/api/device-logs/subscribe", json=payload)
        response2 = client.post("/api/device-logs/subscribe", json=payload)

        assert response1.status_code == 200
        assert response2.status_code == 200


class TestDeviceLogUnsubscribe:
    """Tests for POST /api/device-logs/unsubscribe."""

    def test_unsubscribe_success(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Given active subscription, when POST unsubscribe, then 200."""
        device_id = _setup_device(app, container)

        dls = container.device_log_stream_service()
        dls.bind_identity("req-test-1", {})
        dls.subscribe("req-test-1", "sensor.living_room", None)

        response = client.post(
            "/api/device-logs/unsubscribe",
            json={"request_id": "req-test-1", "device_id": device_id},
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "unsubscribed"

    def test_unsubscribe_no_subscription(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Given no active subscription, when POST unsubscribe, then 404."""
        device_id = _setup_device(app, container)

        dls = container.device_log_stream_service()
        dls.bind_identity("req-test-1", {})

        response = client.post(
            "/api/device-logs/unsubscribe",
            json={"request_id": "req-test-1", "device_id": device_id},
        )

        assert response.status_code == 404

    def test_unsubscribe_no_identity_binding(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Given request_id with no identity binding, when POST unsubscribe, then 403."""
        device_id = _setup_device(app, container)

        response = client.post(
            "/api/device-logs/unsubscribe",
            json={"request_id": "req-no-identity", "device_id": device_id},
        )

        assert response.status_code == 403

    def test_unsubscribe_device_no_entity_id(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Given a device with no entity_id, when POST unsubscribe, then 404."""
        device_id = _setup_device(app, container, entity_id=None)

        dls = container.device_log_stream_service()
        dls.bind_identity("req-test-1", {})

        response = client.post(
            "/api/device-logs/unsubscribe",
            json={"request_id": "req-test-1", "device_id": device_id},
        )

        assert response.status_code == 404
