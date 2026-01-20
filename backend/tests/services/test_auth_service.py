"""Tests for AuthService JWT validation."""

from unittest.mock import MagicMock, patch

import pytest

from app.config import Settings
from app.exceptions import AuthenticationException
from app.services.auth_service import AuthService
from app.services.metrics_service import MetricsService


class TestAuthService:
    """Test suite for AuthService."""

    @pytest.fixture
    def auth_settings(self, test_settings: Settings) -> Settings:
        """Create settings with OIDC enabled."""
        test_settings.OIDC_ENABLED = True
        test_settings.OIDC_ISSUER_URL = "https://auth.example.com/realms/iot"
        test_settings.OIDC_CLIENT_ID = "iot-backend"
        test_settings.OIDC_CLIENT_SECRET = "test-secret"
        return test_settings

    def test_validate_token_success_with_admin_role(
        self, auth_settings, generate_test_jwt, mock_oidc_discovery, mock_jwks
    ):
        """Test successful token validation with admin role."""
        metrics_service = MetricsService()

        # Generate valid token
        token = generate_test_jwt(subject="user-123", roles=["admin"])

        # Mock OIDC discovery and JWKS during AuthService initialization
        with patch("httpx.get") as mock_get:
            # Mock discovery response
            mock_discovery_response = MagicMock()
            mock_discovery_response.json.return_value = mock_oidc_discovery
            mock_discovery_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_discovery_response

            # Mock PyJWKClient to return our test public key
            with patch("app.services.auth_service.PyJWKClient") as mock_jwk_client_class:
                mock_jwk_client = MagicMock()
                mock_signing_key = MagicMock()
                mock_signing_key.key = generate_test_jwt.public_key
                mock_jwk_client.get_signing_key_from_jwt.return_value = mock_signing_key
                mock_jwk_client_class.return_value = mock_jwk_client

                # Create AuthService with mocked dependencies
                auth_service = AuthService(auth_settings, metrics_service)

                # Validate token
                auth_context = auth_service.validate_token(token)

                assert auth_context.subject == "user-123"
                assert auth_context.email == "test@example.com"
                assert auth_context.name == "Test User"
                assert "admin" in auth_context.roles

    def test_validate_token_expired(
        self, auth_settings, generate_test_jwt, mock_oidc_discovery
    ):
        """Test token validation fails for expired token."""
        metrics_service = MetricsService()

        # Generate expired token
        token = generate_test_jwt(expired=True)

        # Mock OIDC discovery during AuthService initialization
        with patch("httpx.get") as mock_get:
            mock_discovery_response = MagicMock()
            mock_discovery_response.json.return_value = mock_oidc_discovery
            mock_discovery_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_discovery_response

            with patch("app.services.auth_service.PyJWKClient") as mock_jwk_client_class:
                mock_jwk_client = MagicMock()
                mock_signing_key = MagicMock()
                mock_signing_key.key = generate_test_jwt.public_key
                mock_jwk_client.get_signing_key_from_jwt.return_value = mock_signing_key
                mock_jwk_client_class.return_value = mock_jwk_client

                # Create AuthService with mocked dependencies
                auth_service = AuthService(auth_settings, metrics_service)

                # Validate token should raise exception
                with pytest.raises(AuthenticationException) as exc_info:
                    auth_service.validate_token(token)

                assert "expired" in str(exc_info.value).lower()

    def test_validate_token_with_asset_uploader_role(
        self, auth_settings, generate_test_jwt, mock_oidc_discovery
    ):
        """Test token validation with asset-uploader role."""
        metrics_service = MetricsService()

        # Generate token with asset-uploader role
        token = generate_test_jwt(roles=["asset-uploader"])

        with patch("httpx.get") as mock_get:
            mock_discovery_response = MagicMock()
            mock_discovery_response.json.return_value = mock_oidc_discovery
            mock_discovery_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_discovery_response

            with patch("app.services.auth_service.PyJWKClient") as mock_jwk_client_class:
                mock_jwk_client = MagicMock()
                mock_signing_key = MagicMock()
                mock_signing_key.key = generate_test_jwt.public_key
                mock_jwk_client.get_signing_key_from_jwt.return_value = mock_signing_key
                mock_jwk_client_class.return_value = mock_jwk_client

                # Create AuthService with mocked dependencies
                auth_service = AuthService(auth_settings, metrics_service)

                auth_context = auth_service.validate_token(token)

                assert "asset-uploader" in auth_context.roles
                assert "admin" not in auth_context.roles

    def test_validate_token_m2m_without_email(
        self, auth_settings, generate_test_jwt, mock_oidc_discovery
    ):
        """Test token validation for M2M client without email."""
        metrics_service = MetricsService()

        # Generate token without email/name (M2M)
        token = generate_test_jwt(email=None, name=None, roles=["admin"])

        with patch("httpx.get") as mock_get:
            mock_discovery_response = MagicMock()
            mock_discovery_response.json.return_value = mock_oidc_discovery
            mock_discovery_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_discovery_response

            with patch("app.services.auth_service.PyJWKClient") as mock_jwk_client_class:
                mock_jwk_client = MagicMock()
                mock_signing_key = MagicMock()
                mock_signing_key.key = generate_test_jwt.public_key
                mock_jwk_client.get_signing_key_from_jwt.return_value = mock_signing_key
                mock_jwk_client_class.return_value = mock_jwk_client

                # Create AuthService with mocked dependencies
                auth_service = AuthService(auth_settings, metrics_service)

                auth_context = auth_service.validate_token(token)

                assert auth_context.email is None
                assert auth_context.name is None
                assert "admin" in auth_context.roles

    def test_validate_token_invalid_signature(
        self, auth_settings, generate_test_jwt, mock_oidc_discovery
    ):
        """Test token validation fails for token with invalid signature."""
        metrics_service = MetricsService()

        # Generate token with invalid signature (signed with wrong key)
        token = generate_test_jwt(invalid_signature=True)

        with patch("httpx.get") as mock_get:
            mock_discovery_response = MagicMock()
            mock_discovery_response.json.return_value = mock_oidc_discovery
            mock_discovery_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_discovery_response

            with patch("app.services.auth_service.PyJWKClient") as mock_jwk_client_class:
                mock_jwk_client = MagicMock()
                mock_signing_key = MagicMock()
                # Use the correct public key - PyJWT will detect signature mismatch
                mock_signing_key.key = generate_test_jwt.public_key
                mock_jwk_client.get_signing_key_from_jwt.return_value = mock_signing_key
                mock_jwk_client_class.return_value = mock_jwk_client

                # Create AuthService with mocked dependencies
                auth_service = AuthService(auth_settings, metrics_service)

                # Validate token should raise exception
                with pytest.raises(AuthenticationException) as exc_info:
                    auth_service.validate_token(token)

                assert "signature" in str(exc_info.value).lower()

    def test_validate_token_invalid_issuer(
        self, auth_settings, generate_test_jwt, mock_oidc_discovery
    ):
        """Test token validation fails for token with wrong issuer."""
        metrics_service = MetricsService()

        # Generate token with invalid issuer
        token = generate_test_jwt(invalid_issuer=True)

        with patch("httpx.get") as mock_get:
            mock_discovery_response = MagicMock()
            mock_discovery_response.json.return_value = mock_oidc_discovery
            mock_discovery_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_discovery_response

            with patch("app.services.auth_service.PyJWKClient") as mock_jwk_client_class:
                mock_jwk_client = MagicMock()
                mock_signing_key = MagicMock()
                mock_signing_key.key = generate_test_jwt.public_key
                mock_jwk_client.get_signing_key_from_jwt.return_value = mock_signing_key
                mock_jwk_client_class.return_value = mock_jwk_client

                # Create AuthService with mocked dependencies
                auth_service = AuthService(auth_settings, metrics_service)

                # Validate token should raise exception
                with pytest.raises(AuthenticationException) as exc_info:
                    auth_service.validate_token(token)

                assert "issuer" in str(exc_info.value).lower()

    def test_validate_token_invalid_audience(
        self, auth_settings, generate_test_jwt, mock_oidc_discovery
    ):
        """Test token validation fails for token with wrong audience."""
        metrics_service = MetricsService()

        # Generate token with invalid audience
        token = generate_test_jwt(invalid_audience=True)

        with patch("httpx.get") as mock_get:
            mock_discovery_response = MagicMock()
            mock_discovery_response.json.return_value = mock_oidc_discovery
            mock_discovery_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_discovery_response

            with patch("app.services.auth_service.PyJWKClient") as mock_jwk_client_class:
                mock_jwk_client = MagicMock()
                mock_signing_key = MagicMock()
                mock_signing_key.key = generate_test_jwt.public_key
                mock_jwk_client.get_signing_key_from_jwt.return_value = mock_signing_key
                mock_jwk_client_class.return_value = mock_jwk_client

                # Create AuthService with mocked dependencies
                auth_service = AuthService(auth_settings, metrics_service)

                # Validate token should raise exception
                with pytest.raises(AuthenticationException) as exc_info:
                    auth_service.validate_token(token)

                assert "audience" in str(exc_info.value).lower()
