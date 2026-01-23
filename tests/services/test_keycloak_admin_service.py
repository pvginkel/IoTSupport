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
