"""Tests for health check API endpoint."""

from unittest.mock import patch

from flask.testing import FlaskClient
from sqlalchemy.orm import Session


class TestHealthCheck:
    """Tests for GET /api/health."""

    def test_health_check_healthy(self, client: FlaskClient, session: Session):
        """Returns 200 when database is accessible."""
        response = client.get("/api/health")

        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "healthy"
        assert data["database"] == "connected"

    def test_health_check_unhealthy_db_not_connected(self, client: FlaskClient, session: Session):
        """Returns 503 when database connection fails."""
        with patch("app.api.health.check_db_connection", return_value=False):
            response = client.get("/api/health")

            assert response.status_code == 503
            data = response.get_json()
            assert data["status"] == "unhealthy"
            assert data["database"] == "disconnected"
            assert "error" in data
