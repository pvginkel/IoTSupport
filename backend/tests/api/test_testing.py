"""Tests for testing API endpoints."""

from collections.abc import Generator

import pytest
from flask import Flask
from flask.testing import FlaskClient

from app import create_app
from app.config import Settings
from app.services.container import ServiceContainer


@pytest.fixture
def testing_settings(config_dir, tmp_path) -> Settings:
    """Create test settings with FLASK_ENV=testing to enable testing endpoints."""

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    # Create temporary assets directory and signing key for tests
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir()

    # Create a valid RSA signing key file for all tests
    signing_key_path = tmp_path / "test_signing_key.pem"
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    signing_key_path.write_bytes(pem)

    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        ESP32_CONFIGS_DIR=config_dir,
        ASSETS_DIR=assets_dir,
        SIGNING_KEY_PATH=signing_key_path,
        TIMESTAMP_TOLERANCE_SECONDS=300,
        SECRET_KEY="test-secret-key",
        CORS_ORIGINS=["http://localhost:3000"],
        FLASK_ENV="testing",  # Enable testing mode
        # OIDC_ENABLED defaults to False - test sessions handle auth in testing mode
    )


@pytest.fixture
def testing_app(testing_settings: Settings) -> Generator[Flask, None, None]:
    """Create Flask app with testing mode enabled."""
    app = create_app(testing_settings)
    yield app


@pytest.fixture
def testing_client(testing_app: Flask) -> FlaskClient:
    """Create test client with testing mode enabled."""
    return testing_app.test_client()


@pytest.fixture
def testing_container(testing_app: Flask) -> ServiceContainer:
    """Access to the DI container for testing."""
    return testing_app.container


@pytest.fixture
def clear_test_sessions(testing_container: ServiceContainer) -> Generator[None, None, None]:
    """Clear test sessions before and after each test.

    Note: Not autouse - only used by tests that need testing_container.
    """
    testing_service = testing_container.testing_service()
    testing_service.clear_all_sessions()
    yield
    testing_service.clear_all_sessions()
    # Also clear any forced errors
    testing_service.consume_forced_auth_error()


class TestTestingEndpointsDisabled:
    """Tests for testing endpoints when not in testing mode."""

    def test_session_endpoint_returns_400_when_not_testing(self, client: FlaskClient):
        """POST /api/testing/auth/session returns 400 when not in testing mode."""
        response = client.post(
            "/api/testing/auth/session",
            json={"subject": "test-user"},
        )

        assert response.status_code == 400
        data = response.get_json()
        assert data["code"] == "ROUTE_NOT_AVAILABLE"
        assert "FLASK_ENV=testing" in data["details"]["message"]

    def test_clear_endpoint_returns_400_when_not_testing(self, client: FlaskClient):
        """POST /api/testing/auth/clear returns 400 when not in testing mode."""
        response = client.post("/api/testing/auth/clear")

        assert response.status_code == 400
        data = response.get_json()
        assert data["code"] == "ROUTE_NOT_AVAILABLE"

    def test_force_error_endpoint_returns_400_when_not_testing(self, client: FlaskClient):
        """POST /api/testing/auth/force-error returns 400 when not in testing mode."""
        response = client.post("/api/testing/auth/force-error?status=500")

        assert response.status_code == 400
        data = response.get_json()
        assert data["code"] == "ROUTE_NOT_AVAILABLE"


@pytest.mark.usefixtures("clear_test_sessions")
class TestCreateTestSession:
    """Tests for POST /api/testing/auth/session."""

    def test_create_session_success(self, testing_client: FlaskClient):
        """Successfully creates a test session with full user data."""
        response = testing_client.post(
            "/api/testing/auth/session",
            json={
                "subject": "test-user-123",
                "name": "Test User",
                "email": "test@example.com",
                "roles": ["admin", "user"],
            },
        )

        assert response.status_code == 201
        data = response.get_json()
        assert data["subject"] == "test-user-123"
        assert data["name"] == "Test User"
        assert data["email"] == "test@example.com"
        assert data["roles"] == ["admin", "user"]

        # Check that cookie is set
        cookies = response.headers.getlist("Set-Cookie")
        assert any("access_token=" in cookie for cookie in cookies)

    def test_create_session_minimal(self, testing_client: FlaskClient):
        """Creates session with only required subject field."""
        response = testing_client.post(
            "/api/testing/auth/session",
            json={"subject": "minimal-user"},
        )

        assert response.status_code == 201
        data = response.get_json()
        assert data["subject"] == "minimal-user"
        assert data["name"] is None
        assert data["email"] is None
        assert data["roles"] == []

    def test_create_session_missing_subject(self, testing_client: FlaskClient):
        """Returns 400 when subject is missing."""
        response = testing_client.post(
            "/api/testing/auth/session",
            json={"name": "Test User"},
        )

        assert response.status_code == 400

    def test_auth_self_returns_test_session_user(self, testing_client: FlaskClient):
        """After creating session, /api/auth/self returns the test user."""
        # Create test session
        testing_client.post(
            "/api/testing/auth/session",
            json={
                "subject": "alice-123",
                "name": "Alice Smith",
                "email": "alice@example.com",
                "roles": ["admin"],
            },
        )

        # Check /api/auth/self returns the test user
        response = testing_client.get("/api/auth/self")

        assert response.status_code == 200
        data = response.get_json()
        assert data["subject"] == "alice-123"
        assert data["name"] == "Alice Smith"
        assert data["email"] == "alice@example.com"
        assert data["roles"] == ["admin"]


@pytest.mark.usefixtures("clear_test_sessions")
class TestClearTestSession:
    """Tests for POST /api/testing/auth/clear."""

    def test_clear_session_success(self, testing_client: FlaskClient):
        """Successfully clears the test session."""
        # First create a session
        testing_client.post(
            "/api/testing/auth/session",
            json={"subject": "user-to-clear"},
        )

        # Clear the session
        response = testing_client.post("/api/testing/auth/clear")

        assert response.status_code == 204

        # Check cookie is cleared
        cookies = response.headers.getlist("Set-Cookie")
        assert any("access_token=" in cookie and "Max-Age=0" in cookie for cookie in cookies)

    def test_clear_session_makes_auth_self_return_401(self, testing_client: FlaskClient):
        """After clearing session, /api/auth/self returns 401."""
        # Create and then clear session
        testing_client.post(
            "/api/testing/auth/session",
            json={"subject": "temp-user"},
        )
        testing_client.post("/api/testing/auth/clear")

        # Check /api/auth/self now returns 401
        response = testing_client.get("/api/auth/self")

        assert response.status_code == 401

    def test_clear_session_without_existing_session(self, testing_client: FlaskClient):
        """Clearing when no session exists returns 204 (idempotent)."""
        response = testing_client.post("/api/testing/auth/clear")

        assert response.status_code == 204


@pytest.mark.usefixtures("clear_test_sessions")
class TestForceAuthError:
    """Tests for POST /api/testing/auth/force-error."""

    def test_force_error_500(self, testing_client: FlaskClient):
        """Forces a 500 error on next /api/auth/self request."""
        # Create a session first
        testing_client.post(
            "/api/testing/auth/session",
            json={"subject": "test-user"},
        )

        # Force a 500 error
        response = testing_client.post("/api/testing/auth/force-error?status=500")
        assert response.status_code == 204

        # Next /api/auth/self should return 500
        response = testing_client.get("/api/auth/self")
        assert response.status_code == 500
        data = response.get_json()
        assert "Simulated error" in data["error"]

    def test_force_error_503(self, testing_client: FlaskClient):
        """Forces a 503 error on next /api/auth/self request."""
        testing_client.post(
            "/api/testing/auth/session",
            json={"subject": "test-user"},
        )

        testing_client.post("/api/testing/auth/force-error?status=503")

        response = testing_client.get("/api/auth/self")
        assert response.status_code == 503

    def test_force_error_is_single_shot(self, testing_client: FlaskClient):
        """Forced error is consumed after one request."""
        testing_client.post(
            "/api/testing/auth/session",
            json={"subject": "test-user"},
        )

        # Force error
        testing_client.post("/api/testing/auth/force-error?status=500")

        # First request gets the error
        response = testing_client.get("/api/auth/self")
        assert response.status_code == 500

        # Second request succeeds normally
        response = testing_client.get("/api/auth/self")
        assert response.status_code == 200
        data = response.get_json()
        assert data["subject"] == "test-user"

    def test_force_error_missing_status(self, testing_client: FlaskClient):
        """Returns 400 when status parameter is missing."""
        response = testing_client.post("/api/testing/auth/force-error")

        assert response.status_code == 400


@pytest.mark.usefixtures("clear_test_sessions")
class TestTestSessionAuthenticationMiddleware:
    """Tests for test session authentication in the middleware."""

    def test_test_session_grants_access_to_protected_endpoints(
        self, testing_client: FlaskClient, testing_container: ServiceContainer
    ):
        """Test sessions grant access to endpoints that require authentication."""
        # Create a test session with admin role
        testing_client.post(
            "/api/testing/auth/session",
            json={
                "subject": "admin-user",
                "roles": ["admin"],
            },
        )

        # Should be able to access a protected endpoint (e.g., configs list)
        response = testing_client.get("/api/configs")

        assert response.status_code == 200

    def test_no_test_session_returns_401_for_protected_endpoints(
        self, testing_client: FlaskClient
    ):
        """Without a test session, protected endpoints return 401."""
        response = testing_client.get("/api/configs")

        assert response.status_code == 401
