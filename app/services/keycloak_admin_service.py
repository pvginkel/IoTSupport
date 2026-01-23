"""Keycloak admin API service for managing device clients."""

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

import httpx

from app.exceptions import ExternalServiceException

if TYPE_CHECKING:
    from app.config import Settings
    from app.services.metrics_service import MetricsService

logger = logging.getLogger(__name__)


@dataclass
class KeycloakClient:
    """Represents a Keycloak client."""

    client_id: str
    secret: str


class KeycloakAdminService:
    """Service for managing Keycloak clients via admin API.

    This is a singleton service that manages the lifecycle of Keycloak clients
    for IoT devices. It handles client creation, secret regeneration, and deletion.
    """

    def __init__(
        self,
        config: "Settings",
        metrics_service: "MetricsService",
    ) -> None:
        """Initialize Keycloak admin service.

        Args:
            config: Application settings containing Keycloak configuration
            metrics_service: Metrics service for recording operations
        """
        self.config = config
        self.metrics_service = metrics_service

        # Cache for admin access token
        self._access_token: str | None = None
        self._token_expires_at: float = 0

        # HTTP client for API calls
        self._http_client = httpx.Client(timeout=10.0)

        # Check if Keycloak is configured
        self.enabled = all([
            config.OIDC_TOKEN_URL,
            config.KEYCLOAK_BASE_URL,
            config.KEYCLOAK_REALM,
            config.KEYCLOAK_ADMIN_CLIENT_ID,
            config.KEYCLOAK_ADMIN_CLIENT_SECRET,
        ])

        if self.enabled:
            logger.info("KeycloakAdminService initialized with URL: %s", config.keycloak_admin_url)
        else:
            logger.warning("KeycloakAdminService disabled - missing configuration")

    def _get_access_token(self) -> str:
        """Get valid admin access token, refreshing if needed.

        Returns:
            Access token string

        Raises:
            ExternalServiceException: If token acquisition fails
        """
        # Return cached token if still valid (with 30s buffer)
        if self._access_token and time.time() < self._token_expires_at - 30:
            return self._access_token

        logger.debug("Acquiring new Keycloak admin access token")
        start_time = time.perf_counter()

        try:
            response = self._http_client.post(
                self.config.OIDC_TOKEN_URL or "",
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.config.KEYCLOAK_ADMIN_CLIENT_ID,
                    "client_secret": self.config.KEYCLOAK_ADMIN_CLIENT_SECRET,
                },
            )
            response.raise_for_status()
            token_data = response.json()

            access_token: str = token_data["access_token"]
            self._access_token = access_token
            # Cache token until it expires
            expires_in = token_data.get("expires_in", 300)
            self._token_expires_at = time.time() + expires_in

            duration = time.perf_counter() - start_time
            logger.debug("Acquired admin token in %.3fs", duration)

            return access_token

        except httpx.HTTPError as e:
            duration = time.perf_counter() - start_time
            logger.error("Failed to acquire admin token: %s (%.3fs)", str(e), duration)
            self._record_operation("get_token", "error")
            raise ExternalServiceException(
                "acquire Keycloak admin token",
                str(e)
            ) from e

    def _record_operation(self, operation: str, status: str) -> None:
        """Record a Keycloak operation metric."""
        self.metrics_service.increment_counter(
            "iot_keycloak_operations_total",
            labels={"operation": operation, "status": status}
        )

    def create_client(self, client_id: str) -> KeycloakClient:
        """Create a new Keycloak client for a device.

        If the client already exists, returns the existing client with its current secret.

        Args:
            client_id: Client ID for the device (format: iotdevice-<model>-<key>)

        Returns:
            KeycloakClient with client_id and secret

        Raises:
            ExternalServiceException: If client creation fails
        """
        if not self.enabled:
            raise ExternalServiceException(
                "create Keycloak client",
                "Keycloak admin API not configured"
            )

        start_time = time.perf_counter()
        token = self._get_access_token()

        # Check if client already exists
        try:
            existing = self._get_client_by_client_id(client_id, token)
            if existing:
                # Client exists, get its secret
                secret = self._get_client_secret(existing["id"], token)
                duration = time.perf_counter() - start_time
                logger.info("Client %s already exists, returning existing secret (%.3fs)", client_id, duration)
                self._record_operation("create_client", "success")
                return KeycloakClient(client_id=client_id, secret=secret)
        except ExternalServiceException:
            # Client doesn't exist, continue with creation
            pass

        # Create new client
        try:
            admin_url = self.config.keycloak_admin_url
            response = self._http_client.post(
                f"{admin_url}/clients",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "clientId": client_id,
                    "enabled": True,
                    "protocol": "openid-connect",
                    "publicClient": False,
                    "serviceAccountsEnabled": True,
                    "standardFlowEnabled": False,
                    "directAccessGrantsEnabled": False,
                },
            )
            response.raise_for_status()

            # Get the internal ID from Location header or re-fetch
            location = response.headers.get("Location", "")
            if location:
                internal_id = location.split("/")[-1]
            else:
                # Re-fetch to get internal ID
                client_data = self._get_client_by_client_id(client_id, token)
                if not client_data:
                    raise ExternalServiceException(
                        "create Keycloak client",
                        "Client created but could not be retrieved"
                    )
                internal_id = client_data["id"]

            # Get the generated secret
            secret = self._get_client_secret(internal_id, token)

            duration = time.perf_counter() - start_time
            logger.info("Created Keycloak client %s in %.3fs", client_id, duration)
            self._record_operation("create_client", "success")

            return KeycloakClient(client_id=client_id, secret=secret)

        except httpx.HTTPError as e:
            duration = time.perf_counter() - start_time
            logger.error("Failed to create Keycloak client %s: %s (%.3fs)", client_id, str(e), duration)
            self._record_operation("create_client", "error")
            raise ExternalServiceException(
                "create Keycloak client",
                str(e)
            ) from e

    def regenerate_secret(self, client_id: str) -> str:
        """Regenerate the secret for an existing Keycloak client.

        Args:
            client_id: Client ID for the device

        Returns:
            New secret string

        Raises:
            ExternalServiceException: If secret regeneration fails
        """
        if not self.enabled:
            raise ExternalServiceException(
                "regenerate Keycloak client secret",
                "Keycloak admin API not configured"
            )

        start_time = time.perf_counter()
        token = self._get_access_token()

        try:
            # Get internal client ID
            client_data = self._get_client_by_client_id(client_id, token)
            if not client_data:
                raise ExternalServiceException(
                    "regenerate Keycloak client secret",
                    f"Client {client_id} not found"
                )

            internal_id = client_data["id"]
            admin_url = self.config.keycloak_admin_url

            # Regenerate secret
            response = self._http_client.post(
                f"{admin_url}/clients/{internal_id}/client-secret",
                headers={"Authorization": f"Bearer {token}"},
            )
            response.raise_for_status()

            secret_data = response.json()
            new_secret: str = secret_data["value"]

            duration = time.perf_counter() - start_time
            logger.info("Regenerated secret for client %s in %.3fs", client_id, duration)
            self._record_operation("regenerate_secret", "success")

            return new_secret

        except httpx.HTTPError as e:
            duration = time.perf_counter() - start_time
            logger.error("Failed to regenerate secret for %s: %s (%.3fs)", client_id, str(e), duration)
            self._record_operation("regenerate_secret", "error")
            raise ExternalServiceException(
                "regenerate Keycloak client secret",
                str(e)
            ) from e

    def get_client_secret(self, client_id: str) -> str:
        """Get the current secret for a Keycloak client.

        Args:
            client_id: Client ID for the device

        Returns:
            Current secret string

        Raises:
            ExternalServiceException: If secret retrieval fails
        """
        if not self.enabled:
            raise ExternalServiceException(
                "get Keycloak client secret",
                "Keycloak admin API not configured"
            )

        token = self._get_access_token()

        try:
            client_data = self._get_client_by_client_id(client_id, token)
            if not client_data:
                raise ExternalServiceException(
                    "get Keycloak client secret",
                    f"Client {client_id} not found"
                )

            internal_id = client_data["id"]
            return self._get_client_secret(internal_id, token)

        except httpx.HTTPError as e:
            logger.error("Failed to get secret for %s: %s", client_id, str(e))
            raise ExternalServiceException(
                "get Keycloak client secret",
                str(e)
            ) from e

    def update_client_secret(self, client_id: str, secret: str) -> None:
        """Update the secret for a Keycloak client to a specific value.

        Used for restoring cached secrets after rotation timeout.

        Args:
            client_id: Client ID for the device
            secret: Secret value to set

        Raises:
            ExternalServiceException: If secret update fails
        """
        if not self.enabled:
            raise ExternalServiceException(
                "update Keycloak client secret",
                "Keycloak admin API not configured"
            )

        start_time = time.perf_counter()
        token = self._get_access_token()

        try:
            # Get internal client ID
            client_data = self._get_client_by_client_id(client_id, token)
            if not client_data:
                raise ExternalServiceException(
                    "update Keycloak client secret",
                    f"Client {client_id} not found"
                )

            internal_id = client_data["id"]
            admin_url = self.config.keycloak_admin_url

            # Update client with new secret
            response = self._http_client.put(
                f"{admin_url}/clients/{internal_id}",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "clientId": client_id,
                    "secret": secret,
                },
            )
            response.raise_for_status()

            duration = time.perf_counter() - start_time
            logger.info("Updated secret for client %s in %.3fs", client_id, duration)
            self._record_operation("update_secret", "success")

        except httpx.HTTPError as e:
            duration = time.perf_counter() - start_time
            logger.error("Failed to update secret for %s: %s (%.3fs)", client_id, str(e), duration)
            self._record_operation("update_secret", "error")
            raise ExternalServiceException(
                "update Keycloak client secret",
                str(e)
            ) from e

    def delete_client(self, client_id: str) -> None:
        """Delete a Keycloak client.

        Args:
            client_id: Client ID for the device

        Raises:
            ExternalServiceException: If client deletion fails
        """
        if not self.enabled:
            raise ExternalServiceException(
                "delete Keycloak client",
                "Keycloak admin API not configured"
            )

        start_time = time.perf_counter()
        token = self._get_access_token()

        try:
            # Get internal client ID
            client_data = self._get_client_by_client_id(client_id, token)
            if not client_data:
                # Client doesn't exist, consider it already deleted
                logger.info("Client %s not found, considering deleted", client_id)
                self._record_operation("delete_client", "success")
                return

            internal_id = client_data["id"]
            admin_url = self.config.keycloak_admin_url

            # Delete client
            response = self._http_client.delete(
                f"{admin_url}/clients/{internal_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
            response.raise_for_status()

            duration = time.perf_counter() - start_time
            logger.info("Deleted Keycloak client %s in %.3fs", client_id, duration)
            self._record_operation("delete_client", "success")

        except httpx.HTTPError as e:
            duration = time.perf_counter() - start_time
            logger.error("Failed to delete client %s: %s (%.3fs)", client_id, str(e), duration)
            self._record_operation("delete_client", "error")
            raise ExternalServiceException(
                "delete Keycloak client",
                str(e)
            ) from e

    def get_client_status(self, client_id: str) -> tuple[bool, str | None]:
        """Check if a client exists in Keycloak.

        Args:
            client_id: Client ID to check

        Returns:
            Tuple of (exists, keycloak_uuid) where keycloak_uuid is the internal
            Keycloak ID if the client exists, None otherwise.

        Raises:
            ExternalServiceException: If Keycloak API call fails
        """
        if not self.enabled:
            raise ExternalServiceException(
                "check Keycloak client status",
                "Keycloak admin API not configured"
            )

        token = self._get_access_token()

        try:
            client_data = self._get_client_by_client_id(client_id, token)
            if client_data:
                return (True, client_data["id"])
            return (False, None)

        except httpx.HTTPError as e:
            logger.error("Failed to check client status for %s: %s", client_id, str(e))
            self._record_operation("get_client_status", "error")
            raise ExternalServiceException(
                "check Keycloak client status",
                str(e)
            ) from e

    def _get_client_by_client_id(self, client_id: str, token: str) -> dict[str, Any] | None:
        """Get client data by client_id (not internal ID).

        Args:
            client_id: The clientId field
            token: Admin access token

        Returns:
            Client data dict or None if not found
        """
        admin_url = self.config.keycloak_admin_url
        response = self._http_client.get(
            f"{admin_url}/clients",
            headers={"Authorization": f"Bearer {token}"},
            params={"clientId": client_id},
        )
        response.raise_for_status()

        clients: list[dict[str, Any]] = response.json()
        if clients:
            return clients[0]
        return None

    def _get_client_secret(self, internal_id: str, token: str) -> str:
        """Get client secret by internal ID.

        Args:
            internal_id: Internal Keycloak client ID (UUID)
            token: Admin access token

        Returns:
            Client secret string
        """
        admin_url = self.config.keycloak_admin_url
        response = self._http_client.get(
            f"{admin_url}/clients/{internal_id}/client-secret",
            headers={"Authorization": f"Bearer {token}"},
        )
        response.raise_for_status()

        secret_data = response.json()
        return cast(str, secret_data["value"])
