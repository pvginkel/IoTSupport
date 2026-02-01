"""Tests for health check API endpoint."""

from unittest.mock import patch

from flask.testing import FlaskClient
from sqlalchemy.orm import Session

from app.services.container import ServiceContainer


class TestHealthCheck:
    """Tests for GET /api/health."""

    def test_health_check_healthy(
        self, client: FlaskClient, session: Session, container: ServiceContainer
    ):
        """Returns 200 when database and MQTT are connected."""
        mqtt_service = container.mqtt_service()
        mqtt_service.enabled = True

        response = client.get("/api/health")

        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "healthy"
        assert data["database"] == "connected"
        assert data["mqtt"] == "connected"
        assert "error" not in data

    def test_health_check_unhealthy_db_not_connected(
        self, client: FlaskClient, session: Session, container: ServiceContainer
    ):
        """Returns 503 when database connection fails."""
        mqtt_service = container.mqtt_service()
        mqtt_service.enabled = True

        with patch("app.api.health.check_db_connection", return_value=False):
            response = client.get("/api/health")

            assert response.status_code == 503
            data = response.get_json()
            assert data["status"] == "unhealthy"
            assert data["database"] == "disconnected"
            assert data["mqtt"] == "connected"
            assert "database not connected" in data["error"]

    def test_health_check_unhealthy_mqtt_not_connected(
        self, client: FlaskClient, session: Session, container: ServiceContainer
    ):
        """Returns 503 when MQTT is not connected."""
        mqtt_service = container.mqtt_service()
        mqtt_service.enabled = False

        response = client.get("/api/health")

        assert response.status_code == 503
        data = response.get_json()
        assert data["status"] == "unhealthy"
        assert data["database"] == "connected"
        assert data["mqtt"] == "disconnected"
        assert "MQTT not connected" in data["error"]

    def test_health_check_unhealthy_both_not_connected(
        self, client: FlaskClient, session: Session, container: ServiceContainer
    ):
        """Returns 503 when both database and MQTT are not connected."""
        mqtt_service = container.mqtt_service()
        mqtt_service.enabled = False

        with patch("app.api.health.check_db_connection", return_value=False):
            response = client.get("/api/health")

            assert response.status_code == 503
            data = response.get_json()
            assert data["status"] == "unhealthy"
            assert data["database"] == "disconnected"
            assert data["mqtt"] == "disconnected"
            assert "database not connected" in data["error"]
            assert "MQTT not connected" in data["error"]
