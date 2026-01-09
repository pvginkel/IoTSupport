"""Tests for health check API endpoint."""

from pathlib import Path

from flask.testing import FlaskClient

from app import create_app
from app.config import Settings


class TestHealthCheck:
    """Tests for GET /api/health."""

    def test_health_check_healthy(self, client: FlaskClient):
        """Returns 200 when config directory is accessible."""
        response = client.get("/api/health")

        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "healthy"

    def test_health_check_unhealthy_dir_not_exists(self, tmp_path: Path):
        """Returns 503 when config directory does not exist."""
        non_existent = tmp_path / "does_not_exist"

        settings = Settings(
            ESP32_CONFIGS_DIR=non_existent,
            SECRET_KEY="test-secret",
            DEBUG=True,
        )
        app = create_app(settings)
        client = app.test_client()

        response = client.get("/api/health")

        assert response.status_code == 503
        data = response.get_json()
        assert data["status"] == "unhealthy"
        assert "does not exist" in data["reason"].lower()

    def test_health_check_unhealthy_not_directory(self, tmp_path: Path):
        """Returns 503 when path is not a directory."""
        file_path = tmp_path / "not_a_dir"
        file_path.touch()

        settings = Settings(
            ESP32_CONFIGS_DIR=file_path,
            SECRET_KEY="test-secret",
            DEBUG=True,
        )
        app = create_app(settings)
        client = app.test_client()

        response = client.get("/api/health")

        assert response.status_code == 503
        data = response.get_json()
        assert data["status"] == "unhealthy"
        assert "not a directory" in data["reason"].lower()
