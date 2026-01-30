"""Tests for KeycloakAdminService."""

from unittest.mock import MagicMock, patch

import httpx
import pytest
from flask import Flask

from app.exceptions import ExternalServiceException
from app.services.container import ServiceContainer


class TestKeycloakAdminServiceUpdateClientMetadata:
    """Tests for update_client_metadata method."""

    def test_update_client_metadata_success(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test updating client name and description."""
        with app.app_context():
            keycloak_service = container.keycloak_admin_service()
            keycloak_service.enabled = True

            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()

            with patch.object(
                keycloak_service,
                "_get_access_token",
                return_value="mock-token"
            ), patch.object(
                keycloak_service,
                "_get_client_by_client_id",
                return_value={"id": "uuid-123", "clientId": "test-client"}
            ), patch.object(
                keycloak_service._http_client,
                "put",
                return_value=mock_response
            ) as mock_put:
                keycloak_service.update_client_metadata(
                    "test-client",
                    name="My Device",
                    description="Test description"
                )

                mock_put.assert_called_once()
                call_args = mock_put.call_args
                assert call_args[1]["json"]["name"] == "My Device"
                assert call_args[1]["json"]["description"] == "Test description"

    def test_update_client_metadata_name_only(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test updating only the client name."""
        with app.app_context():
            keycloak_service = container.keycloak_admin_service()
            keycloak_service.enabled = True

            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()

            with patch.object(
                keycloak_service,
                "_get_access_token",
                return_value="mock-token"
            ), patch.object(
                keycloak_service,
                "_get_client_by_client_id",
                return_value={"id": "uuid-123", "clientId": "test-client"}
            ), patch.object(
                keycloak_service._http_client,
                "put",
                return_value=mock_response
            ) as mock_put:
                keycloak_service.update_client_metadata("test-client", name="My Device")

                call_args = mock_put.call_args
                assert call_args[1]["json"]["name"] == "My Device"
                assert "description" not in call_args[1]["json"]

    def test_update_client_metadata_no_changes_skips(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test that no API call is made when nothing to update."""
        with app.app_context():
            keycloak_service = container.keycloak_admin_service()
            keycloak_service.enabled = True

            with patch.object(
                keycloak_service._http_client,
                "put"
            ) as mock_put:
                keycloak_service.update_client_metadata("test-client")

                mock_put.assert_not_called()

    def test_update_client_metadata_client_not_found(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test error when client doesn't exist."""
        with app.app_context():
            keycloak_service = container.keycloak_admin_service()
            keycloak_service.enabled = True

            with patch.object(
                keycloak_service,
                "_get_access_token",
                return_value="mock-token"
            ), patch.object(
                keycloak_service,
                "_get_client_by_client_id",
                return_value=None
            ):
                with pytest.raises(ExternalServiceException) as exc_info:
                    keycloak_service.update_client_metadata(
                        "missing-client", name="Name"
                    )

                assert "not found" in str(exc_info.value)

    def test_update_client_metadata_disabled_raises(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test error when Keycloak is not configured."""
        with app.app_context():
            keycloak_service = container.keycloak_admin_service()
            keycloak_service.enabled = False

            with pytest.raises(ExternalServiceException) as exc_info:
                keycloak_service.update_client_metadata("any-client", name="Name")

            assert "not configured" in str(exc_info.value)


class TestKeycloakAdminServiceGetClientStatus:
    """Tests for get_client_status method."""

    def test_get_client_status_exists(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test get_client_status when client exists."""
        with app.app_context():
            keycloak_service = container.keycloak_admin_service()
            # Enable the service for this test
            keycloak_service.enabled = True

            # Mock the internal methods
            with patch.object(
                keycloak_service,
                "_get_access_token",
                return_value="mock-token"
            ), patch.object(
                keycloak_service,
                "_get_client_by_client_id",
                return_value={"id": "uuid-123", "clientId": "test-client"}
            ):
                exists, uuid = keycloak_service.get_client_status("test-client")

                assert exists is True
                assert uuid == "uuid-123"

    def test_get_client_status_not_exists(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test get_client_status when client does not exist."""
        with app.app_context():
            keycloak_service = container.keycloak_admin_service()
            keycloak_service.enabled = True

            with patch.object(
                keycloak_service,
                "_get_access_token",
                return_value="mock-token"
            ), patch.object(
                keycloak_service,
                "_get_client_by_client_id",
                return_value=None
            ):
                exists, uuid = keycloak_service.get_client_status("missing-client")

                assert exists is False
                assert uuid is None

    def test_get_client_status_disabled_raises(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test get_client_status when Keycloak is not configured."""
        with app.app_context():
            keycloak_service = container.keycloak_admin_service()
            keycloak_service.enabled = False

            with pytest.raises(ExternalServiceException) as exc_info:
                keycloak_service.get_client_status("any-client")

            assert "not configured" in str(exc_info.value)

    def test_get_client_status_http_error_raises(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test get_client_status when HTTP error occurs."""
        with app.app_context():
            keycloak_service = container.keycloak_admin_service()
            keycloak_service.enabled = True

            with patch.object(
                keycloak_service,
                "_get_access_token",
                return_value="mock-token"
            ), patch.object(
                keycloak_service,
                "_get_client_by_client_id",
                side_effect=httpx.HTTPError("Connection failed")
            ):
                with pytest.raises(ExternalServiceException) as exc_info:
                    keycloak_service.get_client_status("test-client")

                assert "Connection failed" in str(exc_info.value)


class TestKeycloakAdminServiceDeviceScope:
    """Tests for device scope functionality."""

    def test_get_client_scope_by_name_found(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test finding a client scope by name."""
        with app.app_context():
            keycloak_service = container.keycloak_admin_service()
            keycloak_service.enabled = True

            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = [
                {"id": "scope-uuid-1", "name": "other-scope"},
                {"id": "scope-uuid-2", "name": "iot-device-audience"},
            ]

            with patch.object(
                keycloak_service._http_client,
                "get",
                return_value=mock_response
            ):
                result = keycloak_service._get_client_scope_by_name(
                    "iot-device-audience", "mock-token"
                )

                assert result is not None
                assert result["id"] == "scope-uuid-2"
                assert result["name"] == "iot-device-audience"

    def test_get_client_scope_by_name_not_found(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test when client scope doesn't exist."""
        with app.app_context():
            keycloak_service = container.keycloak_admin_service()
            keycloak_service.enabled = True

            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = [
                {"id": "scope-uuid-1", "name": "other-scope"},
            ]

            with patch.object(
                keycloak_service._http_client,
                "get",
                return_value=mock_response
            ):
                result = keycloak_service._get_client_scope_by_name(
                    "missing-scope", "mock-token"
                )

                assert result is None

    def test_add_default_client_scope_success(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test adding a default client scope to a client."""
        with app.app_context():
            keycloak_service = container.keycloak_admin_service()
            keycloak_service.enabled = True

            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()

            with patch.object(
                keycloak_service._http_client,
                "put",
                return_value=mock_response
            ) as mock_put:
                keycloak_service._add_default_client_scope(
                    "client-uuid", "scope-uuid", "mock-token"
                )

                mock_put.assert_called_once()
                call_url = mock_put.call_args[0][0]
                assert "clients/client-uuid/default-client-scopes/scope-uuid" in call_url

    def test_add_device_scopes_to_client_success(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test adding all device scopes to a client when scopes exist."""
        with app.app_context():
            keycloak_service = container.keycloak_admin_service()
            keycloak_service.enabled = True

            # Mock scope lookups - return different UUIDs for each scope
            # Note: 'openid' is not included as it's automatic for OIDC clients
            def mock_get_scope(scope_name: str, token: str) -> dict | None:
                scopes = {
                    "iot-device-audience": {"id": "audience-uuid", "name": "iot-device-audience"},
                    "profile": {"id": "profile-uuid", "name": "profile"},
                    "email": {"id": "email-uuid", "name": "email"},
                }
                return scopes.get(scope_name)

            with patch.object(
                keycloak_service,
                "_get_client_scope_by_name",
                side_effect=mock_get_scope
            ), patch.object(
                keycloak_service,
                "_add_default_client_scope"
            ) as mock_add_scope:
                keycloak_service._add_device_scopes_to_client("client-uuid", "mock-token")

                # All 3 scopes should be added (iot-device-audience, profile, email)
                assert mock_add_scope.call_count == 3

    def test_add_device_scopes_to_client_missing_scopes_skipped(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test that missing scopes are skipped without error."""
        with app.app_context():
            keycloak_service = container.keycloak_admin_service()
            keycloak_service.enabled = True

            with patch.object(
                keycloak_service,
                "_get_client_scope_by_name",
                return_value=None  # All scopes "not found"
            ), patch.object(
                keycloak_service,
                "_add_default_client_scope"
            ) as mock_add_scope:
                # Should not raise, just skip adding missing scopes
                keycloak_service._add_device_scopes_to_client(
                    "client-uuid", "mock-token"
                )

                # No scopes should be added when none exist
                mock_add_scope.assert_not_called()


class TestKeycloakAdminServiceCreateClient:
    """Tests for create_client method with device scope."""

    def test_create_client_adds_device_scope(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test that create_client adds the device scope to new clients."""
        with app.app_context():
            keycloak_service = container.keycloak_admin_service()
            keycloak_service.enabled = True

            mock_post_response = MagicMock()
            mock_post_response.raise_for_status = MagicMock()
            mock_post_response.headers = {"Location": "http://keycloak/clients/new-uuid"}

            with patch.object(
                keycloak_service,
                "_get_access_token",
                return_value="mock-token"
            ), patch.object(
                keycloak_service,
                "_get_client_by_client_id",
                return_value=None  # Client doesn't exist yet
            ), patch.object(
                keycloak_service._http_client,
                "post",
                return_value=mock_post_response
            ), patch.object(
                keycloak_service,
                "_add_device_scopes_to_client"
            ) as mock_add_scope, patch.object(
                keycloak_service,
                "_get_client_secret",
                return_value="generated-secret"
            ):
                result = keycloak_service.create_client("iotdevice-model-12345678")

                # Verify scope was added
                mock_add_scope.assert_called_once_with("new-uuid", "mock-token")

                # Verify client was returned
                assert result.client_id == "iotdevice-model-12345678"
                assert result.secret == "generated-secret"

    def test_create_client_existing_client_also_adds_scope(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test that create_client adds scope even when client already exists (idempotent)."""
        with app.app_context():
            keycloak_service = container.keycloak_admin_service()
            keycloak_service.enabled = True

            with patch.object(
                keycloak_service,
                "_get_access_token",
                return_value="mock-token"
            ), patch.object(
                keycloak_service,
                "_get_client_by_client_id",
                return_value={"id": "existing-uuid", "clientId": "iotdevice-model-12345678"}
            ), patch.object(
                keycloak_service,
                "_add_device_scopes_to_client"
            ) as mock_add_scope, patch.object(
                keycloak_service,
                "_get_client_secret",
                return_value="existing-secret"
            ):
                result = keycloak_service.create_client("iotdevice-model-12345678")

                # Scope should be added even for existing clients (idempotent operation)
                mock_add_scope.assert_called_once_with("existing-uuid", "mock-token")

                # Existing client should be returned
                assert result.client_id == "iotdevice-model-12345678"
                assert result.secret == "existing-secret"
