"""Tests for health check API endpoint."""

from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
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

        # Create valid assets dir and signing key for test
        assets_dir = tmp_path / "assets"
        assets_dir.mkdir()
        signing_key_path = tmp_path / "test_key.pem"
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        signing_key_path.write_bytes(pem)

        settings = Settings(
            _env_file=None,  # type: ignore[call-arg]
            ESP32_CONFIGS_DIR=non_existent,
            ASSETS_DIR=assets_dir,
            SIGNING_KEY_PATH=signing_key_path,
            SECRET_KEY="test-secret",
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

        # Create valid assets dir and signing key for test
        assets_dir = tmp_path / "assets"
        assets_dir.mkdir()
        signing_key_path = tmp_path / "test_key.pem"
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        signing_key_path.write_bytes(pem)

        settings = Settings(
            _env_file=None,  # type: ignore[call-arg]
            ESP32_CONFIGS_DIR=file_path,
            ASSETS_DIR=assets_dir,
            SIGNING_KEY_PATH=signing_key_path,
            SECRET_KEY="test-secret",
        )
        app = create_app(settings)
        client = app.test_client()

        response = client.get("/api/health")

        assert response.status_code == 503
        data = response.get_json()
        assert data["status"] == "unhealthy"
        assert "not a directory" in data["reason"].lower()
