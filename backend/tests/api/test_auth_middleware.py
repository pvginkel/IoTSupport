"""Tests for authentication middleware and authorization logic."""

import time
from collections.abc import Generator
from unittest.mock import MagicMock, patch

import jwt
import pytest
from flask import Flask
from sqlalchemy.pool import StaticPool

from app import create_app
from app.config import Settings


class TestAuthenticationMiddleware:
    """Test suite for authentication middleware behavior."""

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

                # Create database tables for tests
                with app.app_context():
                    from app.extensions import db
                    db.create_all()

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
            "/api/devices", headers={"Authorization": f"Bearer {token}"}
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
        response = client.get("/api/devices")

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
            "/api/devices",
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
        assert client.get("/api/devices").status_code == 200
        # Admin can also access pipeline endpoints (404 is expected without model)
        response = client.get("/api/pipeline/models/nonexistent/firmware-version")
        assert response.status_code == 404  # Not found, not authorization error

    def test_pipeline_role_restricted_to_pipeline_endpoints(
        self, auth_enabled_app, generate_test_jwt
    ):
        """Test pipeline role is restricted to /api/pipeline endpoints only."""
        client = auth_enabled_app.test_client()

        # Generate token with pipeline role
        token = generate_test_jwt(roles=["pipeline"])
        client.set_cookie("access_token", token)

        # Pipeline role can access /api/pipeline endpoints (404 is expected without model)
        response = client.get("/api/pipeline/models/nonexistent/firmware-version")
        assert response.status_code == 404  # Not found, not authorization error

        # Pipeline role cannot access other endpoints
        response = client.get("/api/devices")
        assert response.status_code == 403
        data = response.get_json()
        assert "permission" in data["error"].lower()

    def test_pipeline_role_cannot_get_devices(
        self, auth_enabled_app, generate_test_jwt
    ):
        """Test pipeline role explicitly denied access to GET /api/devices."""
        client = auth_enabled_app.test_client()

        # Generate token with pipeline role
        token = generate_test_jwt(roles=["pipeline"])
        client.set_cookie("access_token", token)

        # GET /api/devices should be forbidden (requires admin role)
        response = client.get("/api/devices")
        assert response.status_code == 403
        data = response.get_json()
        assert "admin" in data["error"]

    def test_no_token_returns_401(self, auth_enabled_app):
        """Test request without token returns 401 Unauthorized."""
        client = auth_enabled_app.test_client()

        # Request without token should fail
        response = client.get("/api/devices")

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
        response = client.get("/api/devices")

        assert response.status_code == 401
        data = response.get_json()
        assert "expired" in data["error"].lower()

    def test_public_endpoints_bypass_authentication(
        self, auth_enabled_app
    ):
        """Test that @public decorator bypasses authentication."""
        client = auth_enabled_app.test_client()

        # Health endpoint is public - should not return auth errors (401/403)
        # May return 503 if MQTT isn't connected in test environment
        response = client.get("/api/health")
        assert response.status_code not in (401, 403)

        # Auth endpoints are public
        response = client.get("/api/auth/self")
        # Will return 401 because endpoint manually checks for token, but passes before_request
        assert response.status_code == 401

    def test_iot_endpoints_bypass_user_authentication(
        self, auth_enabled_app
    ):
        """Test that /api/iot endpoints bypass user authentication via @public decorator.

        IoT endpoints are marked @public to skip user auth, but have their own
        before_request hook for device authentication. Without a device token,
        they return 401 from device auth, not from user auth.
        """
        client = auth_enabled_app.test_client()

        # IoT endpoint without any token - should get past user auth but fail device auth
        response = client.get("/api/iot/config")

        # Should return 401 from device auth, not 403 from user auth (no admin role)
        assert response.status_code == 401
        data = response.get_json()
        # The error should be about missing token, not about admin role
        assert "admin" not in data["error"].lower()

    def test_oidc_disabled_bypasses_authentication(self, test_settings):
        """Test that OIDC_ENABLED=False bypasses all authentication."""
        # Use model_copy to create a new Settings instance with updated values
        settings = test_settings.model_copy(update={
            "database_url": "sqlite://",
            "sqlalchemy_engine_options": {
                "poolclass": StaticPool,
                "connect_args": {"check_same_thread": False},
            },
            "oidc_enabled": False,
        })

        app = create_app(settings)

        # Create database tables for this fresh app
        with app.app_context():
            from app.extensions import db
            db.create_all()

        client = app.test_client()

        # Should access protected endpoints without token
        response = client.get("/api/devices")
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
        response = client.get("/api/devices")

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
        response = client.get("/api/devices")

        assert response.status_code == 403
        data = response.get_json()
        assert "permission" in data["error"].lower()

    def test_pipeline_role_can_access_public_auth_endpoints(
        self, auth_enabled_app, generate_test_jwt
    ):
        """Test pipeline role can access public endpoints like /api/auth/self."""
        client = auth_enabled_app.test_client()

        # Generate token with pipeline role
        token = generate_test_jwt(subject="pipeline-ci", roles=["pipeline"])
        client.set_cookie("access_token", token)

        # /api/auth/self is public but validates token if present
        response = client.get("/api/auth/self")

        # Should succeed and return user info
        assert response.status_code == 200
        data = response.get_json()
        assert data["subject"] == "pipeline-ci"
        assert "pipeline" in data["roles"]


class TestTokenRefreshMiddleware:
    """Test suite for token refresh functionality in authentication middleware."""

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

    @pytest.fixture
    def auth_enabled_app_with_refresh(
        self, auth_enabled_settings: Settings, mock_oidc_discovery, generate_test_jwt
    ) -> Generator[Flask, None, None]:
        """Create Flask app with OIDC enabled and mocked refresh capability."""
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

                with app.app_context():
                    from app.extensions import db
                    db.create_all()

                yield app

    def test_expired_access_token_with_valid_refresh_token_succeeds(
        self, auth_enabled_app_with_refresh, generate_test_jwt
    ):
        """Test that expired access token with valid refresh token refreshes and succeeds."""
        client = auth_enabled_app_with_refresh.test_client()

        # Generate an expired access token
        expired_token = generate_test_jwt(expired=True, roles=["admin"])

        # Generate a valid refresh token (JWT with future exp)
        refresh_exp = int(time.time()) + 86400  # 24 hours
        refresh_payload = {"sub": "test-user", "exp": refresh_exp, "typ": "Refresh"}
        refresh_token = jwt.encode(
            refresh_payload, generate_test_jwt.private_key, algorithm="RS256"
        )

        # Generate a new valid access token for the refresh response
        new_access_token = generate_test_jwt(subject="test-user", roles=["admin"])

        # Mock the refresh token endpoint
        with patch("httpx.post") as mock_post:
            mock_refresh_response = MagicMock()
            mock_refresh_response.json.return_value = {
                "access_token": new_access_token,
                "refresh_token": refresh_token,
                "token_type": "Bearer",
                "expires_in": 300,
            }
            mock_refresh_response.raise_for_status = MagicMock()
            mock_post.return_value = mock_refresh_response

            # Set expired access token and valid refresh token
            client.set_cookie("access_token", expired_token)
            client.set_cookie("refresh_token", refresh_token)

            # Request should succeed after refresh
            response = client.get("/api/devices")

            assert response.status_code == 200

            # Verify refresh endpoint was called
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert "refresh_token" in call_args.kwargs.get("data", {})

    def test_expired_access_token_with_valid_refresh_sets_new_cookies(
        self, auth_enabled_app_with_refresh, generate_test_jwt
    ):
        """Test that successful refresh sets new access and refresh token cookies."""
        client = auth_enabled_app_with_refresh.test_client()

        # Generate an expired access token
        expired_token = generate_test_jwt(expired=True, roles=["admin"])

        # Generate refresh tokens
        refresh_exp = int(time.time()) + 86400
        refresh_payload = {"sub": "test-user", "exp": refresh_exp, "typ": "Refresh"}
        refresh_token = jwt.encode(
            refresh_payload, generate_test_jwt.private_key, algorithm="RS256"
        )

        new_refresh_exp = int(time.time()) + 86400
        new_refresh_payload = {"sub": "test-user", "exp": new_refresh_exp, "typ": "Refresh"}
        new_refresh_token = jwt.encode(
            new_refresh_payload, generate_test_jwt.private_key, algorithm="RS256"
        )

        new_access_token = generate_test_jwt(subject="test-user", roles=["admin"])

        with patch("httpx.post") as mock_post:
            mock_refresh_response = MagicMock()
            mock_refresh_response.json.return_value = {
                "access_token": new_access_token,
                "refresh_token": new_refresh_token,
                "token_type": "Bearer",
                "expires_in": 300,
            }
            mock_refresh_response.raise_for_status = MagicMock()
            mock_post.return_value = mock_refresh_response

            client.set_cookie("access_token", expired_token)
            client.set_cookie("refresh_token", refresh_token)

            response = client.get("/api/devices")

            assert response.status_code == 200

            # Check that new cookies are set
            set_cookie_headers = response.headers.getlist("Set-Cookie")
            cookie_str = " ".join(set_cookie_headers)

            assert "access_token=" in cookie_str
            assert "refresh_token=" in cookie_str

    def test_expired_access_token_without_refresh_token_returns_401(
        self, auth_enabled_app_with_refresh, generate_test_jwt
    ):
        """Test that expired access token without refresh token returns 401."""
        client = auth_enabled_app_with_refresh.test_client()

        # Generate an expired access token
        expired_token = generate_test_jwt(expired=True, roles=["admin"])

        # Set only the expired access token (no refresh token)
        client.set_cookie("access_token", expired_token)

        response = client.get("/api/devices")

        assert response.status_code == 401

    def test_expired_access_token_with_expired_refresh_token_returns_401(
        self, auth_enabled_app_with_refresh, generate_test_jwt
    ):
        """Test that expired access token with failed refresh returns 401 and clears cookies."""
        client = auth_enabled_app_with_refresh.test_client()

        # Generate expired tokens
        expired_access = generate_test_jwt(expired=True, roles=["admin"])

        refresh_exp = int(time.time()) + 86400
        refresh_payload = {"sub": "test-user", "exp": refresh_exp, "typ": "Refresh"}
        refresh_token = jwt.encode(
            refresh_payload, generate_test_jwt.private_key, algorithm="RS256"
        )

        # Mock refresh endpoint to fail (e.g., refresh token revoked)
        with patch("httpx.post") as mock_post:
            import httpx
            mock_post.side_effect = httpx.HTTPStatusError(
                "401 Unauthorized",
                request=MagicMock(),
                response=MagicMock(status_code=401),
            )

            client.set_cookie("access_token", expired_access)
            client.set_cookie("refresh_token", refresh_token)

            response = client.get("/api/devices")

            assert response.status_code == 401

            # Cookies should be cleared
            set_cookie_headers = response.headers.getlist("Set-Cookie")
            cookie_str = " ".join(set_cookie_headers)

            # Both cookies should be cleared (Max-Age=0)
            assert "access_token=" in cookie_str
            assert "Max-Age=0" in cookie_str

    def test_valid_access_token_does_not_trigger_refresh(
        self, auth_enabled_app_with_refresh, generate_test_jwt
    ):
        """Test that valid access token does not trigger refresh."""
        client = auth_enabled_app_with_refresh.test_client()

        # Generate a valid (non-expired) access token
        valid_token = generate_test_jwt(roles=["admin"])

        # Generate a refresh token
        refresh_exp = int(time.time()) + 86400
        refresh_payload = {"sub": "test-user", "exp": refresh_exp, "typ": "Refresh"}
        refresh_token = jwt.encode(
            refresh_payload, generate_test_jwt.private_key, algorithm="RS256"
        )

        with patch("httpx.post") as mock_post:
            client.set_cookie("access_token", valid_token)
            client.set_cookie("refresh_token", refresh_token)

            response = client.get("/api/devices")

            assert response.status_code == 200

            # Refresh endpoint should NOT have been called
            mock_post.assert_not_called()

    def test_no_access_token_with_valid_refresh_token_succeeds(
        self, auth_enabled_app_with_refresh, generate_test_jwt
    ):
        """Test that missing access token with valid refresh token refreshes and succeeds."""
        client = auth_enabled_app_with_refresh.test_client()

        # Generate a valid refresh token
        refresh_exp = int(time.time()) + 86400
        refresh_payload = {"sub": "test-user", "exp": refresh_exp, "typ": "Refresh"}
        refresh_token = jwt.encode(
            refresh_payload, generate_test_jwt.private_key, algorithm="RS256"
        )

        new_access_token = generate_test_jwt(subject="test-user", roles=["admin"])

        with patch("httpx.post") as mock_post:
            mock_refresh_response = MagicMock()
            mock_refresh_response.json.return_value = {
                "access_token": new_access_token,
                "refresh_token": refresh_token,
                "token_type": "Bearer",
                "expires_in": 300,
            }
            mock_refresh_response.raise_for_status = MagicMock()
            mock_post.return_value = mock_refresh_response

            # Only set refresh token, no access token
            client.set_cookie("refresh_token", refresh_token)

            response = client.get("/api/devices")

            assert response.status_code == 200

            # Verify refresh was called
            mock_post.assert_called_once()
