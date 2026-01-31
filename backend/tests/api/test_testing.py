"""Tests for testing API endpoints."""

import sqlite3
from collections.abc import Generator
from pathlib import Path

import pytest
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy.pool import StaticPool

from app import create_app
from app.config import Settings
from app.database import upgrade_database
from app.services.container import ServiceContainer


def _build_testing_settings(tmp_path: Path) -> Settings:
    """Build settings for testing mode tests."""
    # Create temporary assets directory for tests
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir(exist_ok=True)

    return Settings(
        # Flask settings
        secret_key="test-secret-key",
        flask_env="testing",  # Enable testing mode
        debug=True,
        # Database settings
        database_url="sqlite:///:memory:",
        # Firmware storage
        assets_dir=assets_dir,
        # CORS settings
        cors_origins=["http://localhost:3000"],
        # MQTT settings
        mqtt_url="mqtt://mqtt.example.com:1883",
        device_mqtt_url="mqtt://mqtt.example.com:1883",
        mqtt_username=None,
        mqtt_password=None,
        # OIDC settings (disabled)
        baseurl="http://localhost:3200",
        device_baseurl="http://localhost:3200",
        oidc_enabled=False,
        oidc_issuer_url=None,
        oidc_client_id=None,
        oidc_client_secret=None,
        oidc_scopes="openid profile email",
        oidc_audience=None,
        oidc_clock_skew_seconds=30,
        oidc_cookie_name="access_token",
        oidc_cookie_secure=False,
        oidc_cookie_samesite="Lax",
        oidc_refresh_cookie_name="refresh_token",
        # Keycloak Admin API settings
        oidc_token_url="https://auth.example.com/realms/iot/protocol/openid-connect/token",
        keycloak_base_url="https://auth.example.com",
        keycloak_realm="iot",
        keycloak_admin_client_id="iot-admin",
        keycloak_admin_client_secret="admin-secret",
        keycloak_device_scope_name="iot-device-audience",
        keycloak_admin_url="https://auth.example.com/admin/realms/iot",
        keycloak_console_base_url="https://auth.example.com/admin/master/console/#/iot/clients",
        # WiFi credentials for provisioning
        wifi_ssid="TestNetwork",
        wifi_password="test-wifi-password",
        # Logging endpoint
        logging_url="https://logs.example.com/ingest",
        # Rotation settings
        rotation_cron="0 8 1-7 * 6",
        rotation_timeout_seconds=300,
        rotation_critical_threshold_days=7,
        # Fernet key (derived from "test-secret-key" using SHA256 + base64)
        fernet_key="LOrG82NjxiRqZMyoBc1DynoBsU6y_MUyzuw_YPL33xw=",
    )


def _override_settings_for_sqlite(settings: Settings, conn: sqlite3.Connection) -> Settings:
    """Create a copy of settings configured for SQLite with static pool."""
    return settings.model_copy(
        update={
            "database_url": "sqlite://",
            "sqlalchemy_engine_options": {
                "poolclass": StaticPool,
                "creator": lambda: conn,
            },
        }
    )


@pytest.fixture(scope="module")
def testing_template_connection(tmp_path_factory) -> Generator[sqlite3.Connection, None, None]:
    """Create a template SQLite database for testing mode tests."""
    tmp_path = tmp_path_factory.mktemp("testing")
    conn = sqlite3.connect(":memory:", check_same_thread=False)

    settings = _override_settings_for_sqlite(_build_testing_settings(tmp_path), conn)

    template_app = create_app(settings, skip_background_services=True)
    with template_app.app_context():
        upgrade_database(recreate=True)

    yield conn
    conn.close()


@pytest.fixture
def testing_settings(tmp_path) -> Settings:
    """Create test settings with FLASK_ENV=testing to enable testing endpoints."""
    return _build_testing_settings(tmp_path)


@pytest.fixture
def testing_app(testing_settings: Settings, testing_template_connection: sqlite3.Connection) -> Generator[Flask, None, None]:
    """Create Flask app with testing mode enabled and database set up."""
    clone_conn = sqlite3.connect(":memory:", check_same_thread=False)
    testing_template_connection.backup(clone_conn)

    settings = _override_settings_for_sqlite(testing_settings, clone_conn)

    app = create_app(settings, skip_background_services=True)

    try:
        yield app
    finally:
        with app.app_context():
            from app.extensions import db as flask_db
            flask_db.session.remove()
        clone_conn.close()


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

        # Should be able to access a protected endpoint (e.g., devices list)
        response = testing_client.get("/api/devices")

        assert response.status_code == 200

    def test_no_test_session_allows_access_but_no_auth_context(
        self, testing_client: FlaskClient
    ):
        """Without a test session, endpoints work but /api/auth/self returns 401.

        With OIDC disabled, endpoints don't require authentication.
        However, /api/auth/self requires a valid auth context to return user info.
        """
        # Regular endpoints work without auth when OIDC is disabled
        response = testing_client.get("/api/devices")
        assert response.status_code == 200

        # But /api/auth/self returns 401 since there's no auth context
        response = testing_client.get("/api/auth/self")
        assert response.status_code == 401
