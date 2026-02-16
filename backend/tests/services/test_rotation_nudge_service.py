"""Tests for RotationNudgeService."""

from unittest.mock import Mock

from app.services.rotation_nudge_service import RotationNudgeService
from app.services.sse_connection_manager import SSEConnectionManager
from tests.testing_utils import StubLifecycleCoordinator, TestLifecycleCoordinator


def _make_service(
    lifecycle: StubLifecycleCoordinator | None = None,
) -> tuple[RotationNudgeService, Mock]:
    """Create a RotationNudgeService with mocked dependencies.

    Returns:
        Tuple of (service, mock_sse_manager)
    """
    mock_sse = Mock(spec=SSEConnectionManager)
    lc = lifecycle or StubLifecycleCoordinator()

    service = RotationNudgeService(
        sse_connection_manager=mock_sse,
        lifecycle_coordinator=lc,
    )
    return service, mock_sse


class TestBroadcast:
    """Tests for rotation nudge broadcast."""

    def test_broadcast_sends_rotation_updated_event(self) -> None:
        """Broadcast sends rotation-updated event with empty payload."""
        service, mock_sse = _make_service()
        mock_sse.send_event.return_value = True

        result = service.broadcast(source="web")

        assert result is True
        mock_sse.send_event.assert_called_once_with(
            None, {}, event_name="rotation-updated", service_type="rotation"
        )

    def test_broadcast_no_connections(self) -> None:
        """Broadcast returns False when no connections exist."""
        service, mock_sse = _make_service()
        mock_sse.send_event.return_value = False

        result = service.broadcast(source="cronjob")

        assert result is False

    def test_broadcast_during_shutdown(self) -> None:
        """During shutdown, broadcast returns False without sending."""
        lifecycle = TestLifecycleCoordinator()
        service, mock_sse = _make_service(lifecycle=lifecycle)

        lifecycle.simulate_shutdown()

        result = service.broadcast()

        assert result is False
        mock_sse.send_event.assert_not_called()
