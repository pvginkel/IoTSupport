"""Device log stream service for SSE-based real-time log forwarding.

This singleton service manages per-connection device log subscriptions,
identity binding (request_id -> OIDC subject), and SSE event delivery.
It also provides rotation nudge broadcasts.

Key responsibilities:
- Maintain bidirectional subscription maps: request_id <-> device_entity_id
- Bind OIDC identity on SSE connect for subscription authorization
- Forward matching log messages from LogSinkService to subscribed SSE clients
- Broadcast rotation-updated events to all connected clients
- Clean up subscriptions on SSE disconnect
"""

import logging
import threading
from typing import Any

from prometheus_client import Counter, Gauge

from app.exceptions import AuthorizationException, RecordNotFoundException
from app.services.auth_service import AuthService
from app.services.sse_connection_manager import SSEConnectionManager
from app.utils.lifecycle_coordinator import LifecycleCoordinatorProtocol, LifecycleEvent

logger = logging.getLogger(__name__)

# Prometheus metrics for device log streaming
SSE_DEVICE_LOG_SUBSCRIPTIONS_ACTIVE = Gauge(
    "sse_device_log_subscriptions_active",
    "Current number of active device log subscriptions",
)
SSE_DEVICE_LOG_EVENTS_SENT_TOTAL = Counter(
    "sse_device_log_events_sent_total",
    "Total device-logs SSE events sent",
    ["status"],
)
SSE_ROTATION_NUDGE_BROADCAST_TOTAL = Counter(
    "sse_rotation_nudge_broadcast_total",
    "Total rotation-updated broadcasts attempted",
    ["source"],
)
SSE_IDENTITY_BINDING_TOTAL = Counter(
    "sse_identity_binding_total",
    "Total SSE identity binding attempts",
    ["status"],
)

# Sentinel subject used when OIDC is disabled (dev/test mode)
_LOCAL_USER_SUBJECT = "local-user"


class DeviceLogStreamService:
    """Singleton service managing device log SSE subscriptions and rotation nudges.

    This service does not access the database directly. Device lookups
    (device_id -> device_entity_id) happen at the API layer using
    the request-scoped DeviceService. This service receives the resolved
    device_entity_id directly.
    """

    def __init__(
        self,
        sse_connection_manager: SSEConnectionManager,
        auth_service: AuthService,
        lifecycle_coordinator: LifecycleCoordinatorProtocol,
    ) -> None:
        self.sse_connection_manager = sse_connection_manager
        self.auth_service = auth_service
        self._lifecycle_coordinator = lifecycle_coordinator

        # Subscription maps (protected by _lock)
        # Forward: request_id -> set of device_entity_ids
        self._subscriptions_by_request_id: dict[str, set[str]] = {}
        # Reverse: device_entity_id -> set of request_ids
        self._subscriptions_by_entity_id: dict[str, set[str]] = {}
        # Identity map: request_id -> OIDC subject
        self._identity_map: dict[str, str] = {}

        self._is_shutting_down = False
        self._lock = threading.RLock()

        # Register for disconnect cleanup
        self.sse_connection_manager.register_on_disconnect(self._on_disconnect_callback)

        # Register for lifecycle events (shutdown cleanup)
        lifecycle_coordinator.register_lifecycle_notification(self._on_lifecycle_event)

        logger.info("DeviceLogStreamService initialized")

    # ------------------------------------------------------------------
    # Identity binding
    # ------------------------------------------------------------------

    def bind_identity(self, request_id: str, headers: dict[str, str]) -> None:
        """Extract and validate OIDC token from SSE connect headers, storing
        request_id -> subject mapping for later subscription authorization.

        When OIDC is disabled, stores a sentinel subject so subscriptions
        work without authentication.

        Args:
            request_id: SSE connection request ID
            headers: HTTP headers forwarded from the SSE Gateway connect callback
        """
        # When OIDC is disabled, use sentinel subject
        if not self.auth_service.config.oidc_enabled:
            with self._lock:
                self._identity_map[request_id] = _LOCAL_USER_SUBJECT
            SSE_IDENTITY_BINDING_TOTAL.labels(status="skipped").inc()
            logger.debug(
                "Identity binding skipped (OIDC disabled), using sentinel subject",
                extra={"request_id": request_id},
            )
            return

        # Extract access token from headers
        token = self._extract_token_from_headers(headers)
        if not token:
            SSE_IDENTITY_BINDING_TOTAL.labels(status="failed").inc()
            logger.warning(
                "Identity binding failed: no token found in headers",
                extra={"request_id": request_id},
            )
            return

        # Validate token and extract subject
        try:
            auth_context = self.auth_service.validate_token(token)
            with self._lock:
                self._identity_map[request_id] = auth_context.subject
            SSE_IDENTITY_BINDING_TOTAL.labels(status="success").inc()
            logger.info(
                "Identity bound for SSE connection",
                extra={"request_id": request_id, "subject": auth_context.subject},
            )
        except Exception as e:
            SSE_IDENTITY_BINDING_TOTAL.labels(status="failed").inc()
            logger.warning(
                "Identity binding failed: token validation error",
                extra={"request_id": request_id, "error": str(e)},
            )

    def _extract_token_from_headers(self, headers: dict[str, str]) -> str | None:
        """Extract the access token from forwarded headers.

        Checks the Authorization header first (Bearer token), then falls
        back to the OIDC cookie.

        Args:
            headers: HTTP headers dict (case-sensitive keys as forwarded)

        Returns:
            Token string or None if not found
        """
        # Check Authorization header (case-insensitive lookup)
        for key, value in headers.items():
            if key.lower() == "authorization":
                parts = value.split(" ", 1)
                if len(parts) == 2 and parts[0].lower() == "bearer":
                    return parts[1]

        # Fall back to cookie header
        cookie_name = self.auth_service.config.oidc_cookie_name
        for key, value in headers.items():
            if key.lower() == "cookie":
                # Parse cookie string to find the access_token cookie
                for cookie_part in value.split(";"):
                    cookie_part = cookie_part.strip()
                    if "=" in cookie_part:
                        name, _, val = cookie_part.partition("=")
                        if name.strip() == cookie_name:
                            return val.strip()

        return None

    # ------------------------------------------------------------------
    # Subscription management
    # ------------------------------------------------------------------

    def subscribe(
        self,
        request_id: str,
        device_entity_id: str,
        caller_subject: str | None,
    ) -> None:
        """Subscribe an SSE connection to a device's log stream.

        Verifies identity (caller_subject must match the stored identity for
        request_id). Idempotent: subscribing twice to the same device is a no-op.

        Args:
            request_id: SSE connection request ID
            device_entity_id: Device entity ID for MQTT message matching
            caller_subject: OIDC subject of the caller (from g.auth_context),
                or None when OIDC is disabled

        Raises:
            AuthorizationException: If identity verification fails
        """
        with self._lock:
            self._verify_identity(request_id, caller_subject)

            # Add to forward map
            if request_id not in self._subscriptions_by_request_id:
                self._subscriptions_by_request_id[request_id] = set()
            self._subscriptions_by_request_id[request_id].add(device_entity_id)

            # Add to reverse map
            if device_entity_id not in self._subscriptions_by_entity_id:
                self._subscriptions_by_entity_id[device_entity_id] = set()
            self._subscriptions_by_entity_id[device_entity_id].add(request_id)

            # Update gauge
            total = sum(
                len(subs) for subs in self._subscriptions_by_request_id.values()
            )
            SSE_DEVICE_LOG_SUBSCRIPTIONS_ACTIVE.set(total)

        logger.info(
            "Subscribed to device log stream",
            extra={"request_id": request_id, "device_entity_id": device_entity_id},
        )

    def unsubscribe(
        self,
        request_id: str,
        device_entity_id: str,
        caller_subject: str | None,
    ) -> None:
        """Unsubscribe an SSE connection from a device's log stream.

        Verifies identity before removing. Raises if subscription does not exist.

        Args:
            request_id: SSE connection request ID
            device_entity_id: Device entity ID to unsubscribe from
            caller_subject: OIDC subject of the caller

        Raises:
            AuthorizationException: If identity verification fails
            RecordNotFoundException: If subscription does not exist
        """
        with self._lock:
            self._verify_identity(request_id, caller_subject)

            # Check subscription exists
            subs = self._subscriptions_by_request_id.get(request_id)
            if not subs or device_entity_id not in subs:
                raise RecordNotFoundException(
                    "Subscription", device_entity_id
                )

            # Remove from forward map
            subs.discard(device_entity_id)
            if not subs:
                del self._subscriptions_by_request_id[request_id]

            # Remove from reverse map
            reverse_subs = self._subscriptions_by_entity_id.get(device_entity_id)
            if reverse_subs:
                reverse_subs.discard(request_id)
                if not reverse_subs:
                    del self._subscriptions_by_entity_id[device_entity_id]

            # Update gauge
            total = sum(
                len(s) for s in self._subscriptions_by_request_id.values()
            )
            SSE_DEVICE_LOG_SUBSCRIPTIONS_ACTIVE.set(total)

        logger.info(
            "Unsubscribed from device log stream",
            extra={"request_id": request_id, "device_entity_id": device_entity_id},
        )

    def _verify_identity(self, request_id: str, caller_subject: str | None) -> None:
        """Verify that the caller's subject matches the stored identity for request_id.

        Must be called under self._lock.

        Args:
            request_id: SSE connection request ID
            caller_subject: OIDC subject of the caller (None when OIDC disabled)

        Raises:
            AuthorizationException: If no identity is stored or subjects mismatch
        """
        stored_subject = self._identity_map.get(request_id)
        if stored_subject is None:
            raise AuthorizationException(
                "No identity binding for this SSE connection"
            )

        # When OIDC is disabled, caller_subject is None; accept if stored is sentinel
        if caller_subject is None:
            if stored_subject != _LOCAL_USER_SUBJECT:
                raise AuthorizationException(
                    "Identity mismatch for SSE connection"
                )
            return

        if stored_subject != caller_subject:
            raise AuthorizationException(
                "Identity mismatch for SSE connection"
            )

    # ------------------------------------------------------------------
    # Log forwarding
    # ------------------------------------------------------------------

    def forward_logs(self, documents: list[dict[str, Any]]) -> None:
        """Forward parsed log documents to subscribed SSE clients.

        Groups documents by device_entity_id, then sends a batched SSE event
        to each subscribed request_id. Documents without an identifiable
        entity_id field are skipped.

        This method is called from the MQTT callback thread in LogSinkService.
        The lock is held only for copying the subscriber list; SSE sends
        happen outside the lock to avoid blocking.

        Args:
            documents: List of parsed log document dicts from NDJSON batch
        """
        if self._is_shutting_down:
            return

        # Fast path: if there are no subscriptions at all, skip grouping
        with self._lock:
            if not self._subscriptions_by_entity_id:
                return

        # Group documents by entity_id
        docs_by_entity: dict[str, list[dict[str, Any]]] = {}
        for doc in documents:
            entity_id = doc.get("entity_id")
            if not entity_id:
                continue
            if entity_id not in docs_by_entity:
                docs_by_entity[entity_id] = []
            docs_by_entity[entity_id].append(doc)

        if not docs_by_entity:
            return

        # For each entity_id with active subscriptions, send events
        for entity_id, logs in docs_by_entity.items():
            # Copy subscriber list under lock
            with self._lock:
                request_ids = self._subscriptions_by_entity_id.get(entity_id)
                if not request_ids:
                    continue
                targets = list(request_ids)

            # Build event payload
            event_data = {
                "device_entity_id": entity_id,
                "logs": logs,
            }

            # Send to each subscriber outside the lock
            for request_id in targets:
                success = self.sse_connection_manager.send_event(
                    request_id,
                    event_data,
                    event_name="device-logs",
                    service_type="device-logs",
                )
                if success:
                    SSE_DEVICE_LOG_EVENTS_SENT_TOTAL.labels(status="success").inc()
                else:
                    SSE_DEVICE_LOG_EVENTS_SENT_TOTAL.labels(status="error").inc()

    # ------------------------------------------------------------------
    # Rotation nudge
    # ------------------------------------------------------------------

    def broadcast_rotation_nudge(self, source: str = "web") -> bool:
        """Broadcast a rotation-updated SSE event to all connected clients.

        The event payload is empty -- the frontend re-fetches the dashboard
        on receipt.

        Args:
            source: Origin of the nudge for metrics ("web" or "cronjob")

        Returns:
            True if broadcast reached at least one client, False otherwise
        """
        if self._is_shutting_down:
            return False

        SSE_ROTATION_NUDGE_BROADCAST_TOTAL.labels(source=source).inc()

        result = self.sse_connection_manager.send_event(
            None,  # None = broadcast to all connections
            {},
            event_name="rotation-updated",
            service_type="rotation",
        )

        logger.debug(
            "Broadcast rotation nudge",
            extra={"source": source, "delivered": result},
        )
        return result

    # ------------------------------------------------------------------
    # Disconnect cleanup
    # ------------------------------------------------------------------

    def _on_disconnect_callback(self, request_id: str) -> None:
        """Clean up all subscriptions and identity mapping for a disconnected request_id.

        Called by SSEConnectionManager's disconnect observer pattern.

        Args:
            request_id: Disconnected SSE connection request ID
        """
        with self._lock:
            # Remove all subscriptions for this request_id
            entity_ids = self._subscriptions_by_request_id.pop(request_id, set())
            for entity_id in entity_ids:
                reverse_subs = self._subscriptions_by_entity_id.get(entity_id)
                if reverse_subs:
                    reverse_subs.discard(request_id)
                    if not reverse_subs:
                        del self._subscriptions_by_entity_id[entity_id]

            # Remove identity mapping
            self._identity_map.pop(request_id, None)

            # Update gauge
            total = sum(
                len(s) for s in self._subscriptions_by_request_id.values()
            )
            SSE_DEVICE_LOG_SUBSCRIPTIONS_ACTIVE.set(total)

        if entity_ids:
            logger.info(
                "Cleaned up subscriptions on disconnect",
                extra={
                    "request_id": request_id,
                    "removed_subscriptions": len(entity_ids),
                },
            )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _on_lifecycle_event(self, event: LifecycleEvent) -> None:
        """Handle lifecycle events for shutdown cleanup."""
        match event:
            case LifecycleEvent.PREPARE_SHUTDOWN:
                with self._lock:
                    self._is_shutting_down = True
                    self._subscriptions_by_request_id.clear()
                    self._subscriptions_by_entity_id.clear()
                    self._identity_map.clear()
                    SSE_DEVICE_LOG_SUBSCRIPTIONS_ACTIVE.set(0)
                logger.info("DeviceLogStreamService: PREPARE_SHUTDOWN - cleared all state")
