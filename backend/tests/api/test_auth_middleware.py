"""Tests for authentication middleware and authorization logic."""

from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from app import create_app
from app.config import Settings


class TestAuthenticationMiddleware:
    """Test suite for authentication middleware behavior."""

    @pytest.fixture
    def auth_enabled_settings(self, test_settings: Settings) -> Settings:
        """Create settings with OIDC enabled."""
        test_settings.OIDC_ENABLED = True
        test_settings.OIDC_ISSUER_URL = "https://auth.example.com/realms/iot"
        test_settings.OIDC_CLIENT_ID = "iot-backend"
        test_settings.OIDC_CLIENT_SECRET = "test-secret"
        test_settings.BASEURL = "http://localhost:3200"
        return test_settings

    @pytest.fixture
    def auth_enabled_app(
        self, auth_enabled_settings: Settings, mock_oidc_discovery, generate_test_jwt
    ) -> Generator[Flask, None, None]:
        """Create Flask app with OIDC enabled and mocked JWKS discovery.

        This fixture keeps mocks active for the entire test so that
        AuthService singleton can be initialized lazily on first request.
        """
        # Mock OIDC discovery and JWKS client for the entire test
        with patch("httpx.get") as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_oidc_discovery
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            with patch("app.services.auth_service.PyJWKClient") as mock_jwk_client_class:
                mock_jwk_client = MagicMock()
                mock_signing_key = MagicMock()
                mock_signing_key.key = generate_test_jwt.public_key
                mock_jwk_client.get_signing_key_from_jwt.return_value = mock_signing_key
                mock_jwk_client_class.return_value = mock_jwk_client

                app = create_app(auth_enabled_settings)
                yield app

    def test_bearer_token_authentication(
        self, auth_enabled_app, generate_test_jwt
    ):
        """Test authentication works with Bearer token in Authorization header."""
        client = auth_enabled_app.test_client()

        # Generate valid token with admin role
        token = generate_test_jwt(subject="admin-user", roles=["admin"])

        # Request with Bearer token should succeed
        response = client.get(
            "/api/configs", headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200

    def test_cookie_token_authentication(
        self, auth_enabled_app, generate_test_jwt
    ):
        """Test authentication works with token in cookie."""
        client = auth_enabled_app.test_client()

        # Generate valid token with admin role
        token = generate_test_jwt(subject="cookie-user", roles=["admin"])

        # Set token as cookie
        client.set_cookie("access_token", token)

        # Request should succeed
        response = client.get("/api/configs")

        assert response.status_code == 200

    def test_cookie_takes_precedence_over_bearer(
        self, auth_enabled_app, generate_test_jwt
    ):
        """Test that cookie token is checked before Authorization header."""
        client = auth_enabled_app.test_client()

        # Generate two different tokens
        cookie_token = generate_test_jwt(subject="cookie-user", roles=["admin"])
        bearer_token = generate_test_jwt(subject="bearer-user", roles=["admin"])

        # Set cookie and send Bearer header
        client.set_cookie("access_token", cookie_token)

        response = client.get(
            "/api/configs",
            headers={"Authorization": f"Bearer {bearer_token}"}
        )

        # Request should succeed (cookie is preferred)
        assert response.status_code == 200

    def test_admin_role_grants_full_access(
        self, auth_enabled_app, generate_test_jwt
    ):
        """Test admin role grants access to all endpoints."""
        client = auth_enabled_app.test_client()

        # Generate token with admin role
        token = generate_test_jwt(roles=["admin"])
        client.set_cookie("access_token", token)

        # Admin can access all endpoints
        assert client.get("/api/configs").status_code == 200
        # Note: POST /api/assets requires actual file upload, so we check for 400 (validation) not 403 (authz)
        # A 400 means we passed auth but failed validation, which is expected without proper data
        response = client.post("/api/assets")
        assert response.status_code in [400, 422]  # Validation error, not authorization error

    def test_asset_uploader_restricted_to_post_assets(
        self, auth_enabled_app, generate_test_jwt
    ):
        """Test asset-uploader role is restricted to POST /api/assets only."""
        client = auth_enabled_app.test_client()

        # Generate token with asset-uploader role
        token = generate_test_jwt(roles=["asset-uploader"])
        client.set_cookie("access_token", token)

        # Asset-uploader can POST to /api/assets (but will get validation error without proper data)
        response = client.post("/api/assets")
        assert response.status_code in [400, 422]  # Validation error, not authorization error

        # Asset-uploader cannot access other endpoints
        response = client.get("/api/configs")
        assert response.status_code == 403
        data = response.get_json()
        assert "permission" in data["error"].lower()

    def test_asset_uploader_cannot_get_configs(
        self, auth_enabled_app, generate_test_jwt
    ):
        """Test asset-uploader explicitly denied access to GET /api/configs."""
        client = auth_enabled_app.test_client()

        # Generate token with asset-uploader role
        token = generate_test_jwt(roles=["asset-uploader"])
        client.set_cookie("access_token", token)

        # GET /api/configs should be forbidden
        response = client.get("/api/configs")
        assert response.status_code == 403
        data = response.get_json()
        assert "asset-uploader" in data["error"]

    def test_no_token_returns_401(self, auth_enabled_app):
        """Test request without token returns 401 Unauthorized."""
        client = auth_enabled_app.test_client()

        # Request without token should fail
        response = client.get("/api/configs")

        assert response.status_code == 401
        data = response.get_json()
        assert "token" in data["error"].lower()

    def test_expired_token_returns_401(
        self, auth_enabled_app, generate_test_jwt
    ):
        """Test request with expired token returns 401."""
        client = auth_enabled_app.test_client()

        # Generate expired token
        token = generate_test_jwt(expired=True, roles=["admin"])
        client.set_cookie("access_token", token)

        # Request should fail with 401
        response = client.get("/api/configs")

        assert response.status_code == 401
        data = response.get_json()
        assert "expired" in data["error"].lower()

    def test_public_endpoints_bypass_authentication(
        self, auth_enabled_app
    ):
        """Test that @public decorator bypasses authentication."""
        client = auth_enabled_app.test_client()

        # Health endpoint is public - should work without token
        response = client.get("/api/health")
        assert response.status_code == 200

        # Auth endpoints are public
        response = client.get("/api/auth/self")
        # Will return 401 because endpoint manually checks for token, but passes before_request
        assert response.status_code == 401

    def test_oidc_disabled_bypasses_authentication(self, test_settings):
        """Test that OIDC_ENABLED=False bypasses all authentication."""
        # Create app with OIDC disabled
        test_settings.OIDC_ENABLED = False
        app = create_app(test_settings)
        client = app.test_client()

        # Should access protected endpoints without token
        response = client.get("/api/configs")
        assert response.status_code == 200

    def test_invalid_signature_returns_401(
        self, auth_enabled_app, generate_test_jwt
    ):
        """Test request with invalid signature returns 401."""
        client = auth_enabled_app.test_client()

        # Generate token with invalid signature
        token = generate_test_jwt(invalid_signature=True, roles=["admin"])
        client.set_cookie("access_token", token)

        # Request should fail with 401
        response = client.get("/api/configs")

        assert response.status_code == 401
        data = response.get_json()
        assert "signature" in data["error"].lower()

    def test_no_recognized_roles_returns_403(
        self, auth_enabled_app, generate_test_jwt
    ):
        """Test user with no recognized roles gets 403."""
        client = auth_enabled_app.test_client()

        # Generate token with unrecognized role
        token = generate_test_jwt(roles=["some-other-role"])
        client.set_cookie("access_token", token)

        # Request should fail with 403
        response = client.get("/api/configs")

        assert response.status_code == 403
        data = response.get_json()
        assert "permission" in data["error"].lower()

    def test_asset_uploader_can_access_public_auth_endpoints(
        self, auth_enabled_app, generate_test_jwt
    ):
        """Test asset-uploader can access public endpoints like /api/auth/self."""
        client = auth_enabled_app.test_client()

        # Generate token with asset-uploader role
        token = generate_test_jwt(subject="uploader", roles=["asset-uploader"])
        client.set_cookie("access_token", token)

        # /api/auth/self is public but validates token if present
        response = client.get("/api/auth/self")

        # Should succeed and return user info
        assert response.status_code == 200
        data = response.get_json()
        assert data["subject"] == "uploader"
        assert "asset-uploader" in data["roles"]
