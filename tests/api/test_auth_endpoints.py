"""Tests for authentication endpoints."""


import pytest

from app.config import Settings


class TestAuthEndpoints:
    """Test suite for authentication endpoints."""

    @pytest.fixture
    def auth_enabled_settings(self, test_settings: Settings) -> Settings:
        """Create settings with OIDC enabled."""
        test_settings.OIDC_ENABLED = True
        test_settings.OIDC_ISSUER_URL = "https://auth.example.com/realms/iot"
        test_settings.OIDC_CLIENT_ID = "iot-backend"
        test_settings.OIDC_CLIENT_SECRET = "test-secret"
        test_settings.BASEURL = "http://localhost:3200"
        return test_settings

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

            app = create_app(auth_enabled_settings)
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

            app = create_app(auth_enabled_settings)
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

            app = create_app(auth_enabled_settings)
            client = app.test_client()

            response = client.get("/api/auth/login?redirect=https://evil.com")

            assert response.status_code == 400

    def test_logout_clears_cookie(self, client):
        """Test /api/auth/logout clears access token cookie."""
        response = client.get("/api/auth/logout")

        assert response.status_code == 302
        # Check that cookie is cleared (max_age=0)
        set_cookie_header = response.headers.get("Set-Cookie", "")
        assert "access_token=" in set_cookie_header
        assert "Max-Age=0" in set_cookie_header
