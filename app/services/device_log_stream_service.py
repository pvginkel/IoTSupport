"""Device log stream service for SSE-based real-time log forwarding.

This singleton service manages per-connection device log subscriptions
and SSE event delivery. Identity binding is handled by SSEConnectionManager;
this service queries connection info for authorization checks.

Key responsibilities:
- Maintain bidirectional subscription maps: request_id <-> device_entity_id
- Verify caller identity against SSEConnectionManager on subscribe/unsubscribe
- Forward matching log messages from LogSinkService to subscribed SSE clients
- Clean up subscriptions on SSE disconnect
"""

import logging
import threading
from typing import Any

from prometheus_client import Counter, Gauge

from app.exceptions import AuthorizationException, RecordNotFoundException
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


class DeviceLogStreamService:
    """Singleton service managing device log SSE subscriptions.

    This service does not access the database directly. Device lookups
    (device_id -> device_entity_id) happen at the API layer using
    the request-scoped DeviceService. Identity verification is delegated
    to SSEConnectionManager which owns the request_id -> subject mapping.
    """

    def __init__(
        self,
        sse_connection_manager: SSEConnectionManager,
        lifecycle_coordinator: LifecycleCoordinatorProtocol,
    ) -> None:
        self.sse_connection_manager = sse_connection_manager
        self._lifecycle_coordinator = lifecycle_coordinator

        # Subscription maps (protected by _lock)
        # Forward: request_id -> set of device_entity_ids
        self._subscriptions_by_request_id: dict[str, set[str]] = {}
        # Reverse: device_entity_id -> set of request_ids
        self._subscriptions_by_entity_id: dict[str, set[str]] = {}

        self._is_shutting_down = False
        self._lock = threading.RLock()

        # Register for disconnect cleanup
        self.sse_connection_manager.register_on_disconnect(self._on_disconnect_callback)

        # Register for lifecycle events (shutdown cleanup)
        lifecycle_coordinator.register_lifecycle_notification(self._on_lifecycle_event)

        logger.info("DeviceLogStreamService initialized")

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

        Queries SSEConnectionManager for connection info. The connection must
        exist and have a bound identity. When caller_subject is None (OIDC
        disabled), any bound identity is accepted.

        Args:
            request_id: SSE connection request ID
            caller_subject: OIDC subject of the caller (None when OIDC disabled)

        Raises:
            AuthorizationException: If no identity is stored or subjects mismatch
        """
        conn_info = self.sse_connection_manager.get_connection_info(request_id)
        if conn_info is None or conn_info.subject is None:
            raise AuthorizationException(
                "No identity binding for this SSE connection"
            )

        # When OIDC is disabled, caller_subject is None; accept any bound identity
        if caller_subject is None:
            return

        if conn_info.subject != caller_subject:
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
    # Disconnect cleanup
    # ------------------------------------------------------------------

    def _on_disconnect_callback(self, request_id: str) -> None:
        """Clean up all subscriptions for a disconnected request_id.

        Called by SSEConnectionManager's disconnect observer pattern.
        Identity cleanup is handled by SSEConnectionManager itself.

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
                    SSE_DEVICE_LOG_SUBSCRIPTIONS_ACTIVE.set(0)
                logger.info("DeviceLogStreamService: PREPARE_SHUTDOWN - cleared all state")
