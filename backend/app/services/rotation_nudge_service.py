"""Rotation nudge service for SSE-based dashboard refresh notifications.

This singleton service broadcasts lightweight 'rotation-updated' SSE events
to all connected clients when rotation state changes. The frontend re-fetches
dashboard data on receipt.
"""

import logging

from prometheus_client import Counter

from app.services.sse_connection_manager import SSEConnectionManager
from app.utils.lifecycle_coordinator import LifecycleCoordinatorProtocol, LifecycleEvent

logger = logging.getLogger(__name__)

SSE_ROTATION_NUDGE_BROADCAST_TOTAL = Counter(
    "sse_rotation_nudge_broadcast_total",
    "Total rotation-updated broadcasts attempted",
    ["source"],
)


class RotationNudgeService:
    """Singleton service that broadcasts rotation-updated SSE events."""

    def __init__(
        self,
        sse_connection_manager: SSEConnectionManager,
        lifecycle_coordinator: LifecycleCoordinatorProtocol,
    ) -> None:
        self.sse_connection_manager = sse_connection_manager
        self._is_shutting_down = False

        lifecycle_coordinator.register_lifecycle_notification(self._on_lifecycle_event)

        logger.info("RotationNudgeService initialized")

    def broadcast(self, source: str = "web") -> bool:
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

    def _on_lifecycle_event(self, event: LifecycleEvent) -> None:
        """Handle lifecycle events for shutdown."""
        match event:
            case LifecycleEvent.PREPARE_SHUTDOWN:
                self._is_shutting_down = True
                logger.info("RotationNudgeService: PREPARE_SHUTDOWN")
