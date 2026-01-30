"""Tests for authentication endpoints."""


import pytest
from sqlalchemy.pool import StaticPool

from app.config import Settings


class TestAuthEndpoints:
    """Test suite for authentication endpoints."""

    @pytest.fixture
    def auth_enabled_settings(self, test_settings: Settings) -> Settings:
        """Create settings with OIDC enabled and SQLite support."""
        # Use model_copy to create a new Settings instance with updated values
        return test_settings.model_copy(update={
            "database_url": "sqlite://",
            "sqlalchemy_engine_options": {
                "poolclass": StaticPool,
                "connect_args": {"check_same_thread": False},
            },
            "oidc_enabled": True,
            "oidc_issuer_url": "https://auth.example.com/realms/iot",
            "oidc_client_id": "iot-backend",
            "oidc_client_secret": "test-secret",
            "baseurl": "http://localhost:3200",
        })

    def test_get_current_user_with_oidc_disabled(self, client):
        """Test /api/auth/self returns default user when OIDC disabled."""
        response = client.get("/api/auth/self")

        assert response.status_code == 200
        data = response.get_json()
        assert data["subject"] == "local-user"
        assert data["email"] == "admin@local"
        assert "admin" in data["roles"]

    def test_get_current_user_unauthenticated(self, auth_enabled_settings, mock_oidc_discovery):
        """Test /api/auth/self returns 401 when not authenticated."""
        from unittest.mock import MagicMock, patch

        from app import create_app

        # Mock OIDC discovery during app creation
        with patch("httpx.get") as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_oidc_discovery
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            app = create_app(auth_enabled_settings, skip_background_services=True)

            # Create database tables for this fresh app
            with app.app_context():
                from app.extensions import db
                db.create_all()

            client = app.test_client()

            response = client.get("/api/auth/self")

            assert response.status_code == 401

    def test_login_without_redirect_parameter(self, auth_enabled_settings, mock_oidc_discovery):
        """Test /api/auth/login returns 400 without redirect parameter."""
        from unittest.mock import MagicMock, patch

        from app import create_app

        with patch("httpx.get") as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_oidc_discovery
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            app = create_app(auth_enabled_settings, skip_background_services=True)

            # Create database tables for this fresh app
            with app.app_context():
                from app.extensions import db
                db.create_all()

            client = app.test_client()

            response = client.get("/api/auth/login")

            assert response.status_code == 400
            data = response.get_json()
            assert "redirect" in data["error"].lower()

    def test_login_with_external_redirect_blocked(self, auth_enabled_settings, mock_oidc_discovery):
        """Test /api/auth/login blocks external redirect URLs."""
        from unittest.mock import MagicMock, patch

        from app import create_app

        with patch("httpx.get") as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_oidc_discovery
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            app = create_app(auth_enabled_settings, skip_background_services=True)

            # Create database tables for this fresh app
            with app.app_context():
                from app.extensions import db
                db.create_all()

            client = app.test_client()

            response = client.get("/api/auth/login?redirect=https://evil.com")

            assert response.status_code == 400

    def test_logout_clears_cookie(self, client):
        """Test /api/auth/logout clears access token cookie."""
        response = client.get("/api/auth/logout")

        assert response.status_code == 302
        # Check that cookies are cleared (max_age=0)
        set_cookie_headers = response.headers.getlist("Set-Cookie")
        cookie_str = " ".join(set_cookie_headers)

        assert "access_token=" in cookie_str
        assert "refresh_token=" in cookie_str
        assert "Max-Age=0" in cookie_str

    def test_logout_clears_refresh_token_cookie(self, client):
        """Test /api/auth/logout clears refresh token cookie."""
        # Set a refresh token cookie first
        client.set_cookie("refresh_token", "some-refresh-token")

        response = client.get("/api/auth/logout")

        assert response.status_code == 302

        # Check that refresh_token cookie is cleared
        set_cookie_headers = response.headers.getlist("Set-Cookie")
        refresh_cookie_found = False
        for header in set_cookie_headers:
            if "refresh_token=" in header and "Max-Age=0" in header:
                refresh_cookie_found = True
                break

        assert refresh_cookie_found, "refresh_token cookie should be cleared on logout"
