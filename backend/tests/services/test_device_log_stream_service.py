"""Tests for DeviceLogStreamService."""

from unittest.mock import Mock

import pytest

from app.config import Settings
from app.exceptions import AuthorizationException, RecordNotFoundException
from app.services.auth_service import AuthContext, AuthService
from app.services.device_log_stream_service import (
    _LOCAL_USER_SUBJECT,
    DeviceLogStreamService,
)
from app.services.sse_connection_manager import SSEConnectionManager
from tests.testing_utils import StubLifecycleCoordinator, TestLifecycleCoordinator


def _make_mock_auth_service(oidc_enabled: bool = False) -> Mock:
    """Create a mock AuthService with configurable OIDC state."""
    mock = Mock(spec=AuthService)
    mock.config = Mock(spec=Settings)
    mock.config.oidc_enabled = oidc_enabled
    mock.config.oidc_cookie_name = "access_token"
    return mock


def _make_service(
    oidc_enabled: bool = False,
    lifecycle: StubLifecycleCoordinator | None = None,
) -> tuple[DeviceLogStreamService, Mock, Mock]:
    """Create a DeviceLogStreamService with mocked dependencies.

    Returns:
        Tuple of (service, mock_sse_manager, mock_auth_service)
    """
    mock_sse = Mock(spec=SSEConnectionManager)
    mock_auth = _make_mock_auth_service(oidc_enabled=oidc_enabled)
    lc = lifecycle or StubLifecycleCoordinator()

    service = DeviceLogStreamService(
        sse_connection_manager=mock_sse,
        auth_service=mock_auth,
        lifecycle_coordinator=lc,
    )
    return service, mock_sse, mock_auth


class TestIdentityBinding:
    """Tests for identity binding on SSE connect."""

    def test_bind_identity_oidc_disabled_stores_sentinel(self) -> None:
        """When OIDC is disabled, bind_identity stores the sentinel subject."""
        service, _, _ = _make_service(oidc_enabled=False)

        service.bind_identity("req-1", {})

        assert service._identity_map["req-1"] == _LOCAL_USER_SUBJECT

    def test_bind_identity_oidc_enabled_with_valid_bearer_token(self) -> None:
        """When OIDC is enabled and a valid Bearer token is in headers,
        the subject from token validation is stored."""
        service, _, mock_auth = _make_service(oidc_enabled=True)
        mock_auth.validate_token.return_value = AuthContext(
            subject="user-123", email="user@test.com", name="Test User", roles=set()
        )

        service.bind_identity("req-1", {"Authorization": "Bearer test-token"})

        mock_auth.validate_token.assert_called_once_with("test-token")
        assert service._identity_map["req-1"] == "user-123"

    def test_bind_identity_oidc_enabled_with_cookie(self) -> None:
        """When OIDC is enabled and token is in cookie header, it is extracted."""
        service, _, mock_auth = _make_service(oidc_enabled=True)
        mock_auth.validate_token.return_value = AuthContext(
            subject="user-456", email=None, name=None, roles=set()
        )

        service.bind_identity(
            "req-1",
            {"Cookie": "other=foo; access_token=cookie-token; session=bar"},
        )

        mock_auth.validate_token.assert_called_once_with("cookie-token")
        assert service._identity_map["req-1"] == "user-456"

    def test_bind_identity_oidc_enabled_no_token_in_headers(self) -> None:
        """When OIDC is enabled but no token found, identity map is NOT populated."""
        service, _, mock_auth = _make_service(oidc_enabled=True)

        service.bind_identity("req-1", {"X-Custom": "value"})

        mock_auth.validate_token.assert_not_called()
        assert "req-1" not in service._identity_map

    def test_bind_identity_oidc_enabled_invalid_token(self) -> None:
        """When OIDC is enabled and token validation fails, identity map is NOT populated."""
        service, _, mock_auth = _make_service(oidc_enabled=True)
        mock_auth.validate_token.side_effect = Exception("Token expired")

        service.bind_identity("req-1", {"Authorization": "Bearer bad-token"})

        assert "req-1" not in service._identity_map

    def test_bind_identity_bearer_takes_priority_over_cookie(self) -> None:
        """Bearer Authorization header takes priority over cookie."""
        service, _, mock_auth = _make_service(oidc_enabled=True)
        mock_auth.validate_token.return_value = AuthContext(
            subject="bearer-user", email=None, name=None, roles=set()
        )

        service.bind_identity(
            "req-1",
            {
                "Authorization": "Bearer bearer-token",
                "Cookie": "access_token=cookie-token",
            },
        )

        mock_auth.validate_token.assert_called_once_with("bearer-token")


class TestSubscription:
    """Tests for subscribe/unsubscribe operations."""

    def test_subscribe_success(self) -> None:
        """Subscribe with matching subject stores in both maps."""
        service, _, _ = _make_service(oidc_enabled=False)
        service.bind_identity("req-1", {})

        service.subscribe("req-1", "sensor.living_room", None)

        assert "sensor.living_room" in service._subscriptions_by_request_id["req-1"]
        assert "req-1" in service._subscriptions_by_entity_id["sensor.living_room"]

    def test_subscribe_idempotent(self) -> None:
        """Subscribing same (request_id, entity_id) pair twice is a no-op."""
        service, _, _ = _make_service(oidc_enabled=False)
        service.bind_identity("req-1", {})

        service.subscribe("req-1", "sensor.a", None)
        service.subscribe("req-1", "sensor.a", None)

        assert len(service._subscriptions_by_request_id["req-1"]) == 1
        assert len(service._subscriptions_by_entity_id["sensor.a"]) == 1

    def test_subscribe_multiple_devices(self) -> None:
        """A single connection can subscribe to multiple devices."""
        service, _, _ = _make_service(oidc_enabled=False)
        service.bind_identity("req-1", {})

        service.subscribe("req-1", "sensor.a", None)
        service.subscribe("req-1", "sensor.b", None)

        assert service._subscriptions_by_request_id["req-1"] == {"sensor.a", "sensor.b"}

    def test_subscribe_multiple_connections_same_device(self) -> None:
        """Multiple connections can subscribe to the same device."""
        service, _, _ = _make_service(oidc_enabled=False)
        service.bind_identity("req-1", {})
        service.bind_identity("req-2", {})

        service.subscribe("req-1", "sensor.a", None)
        service.subscribe("req-2", "sensor.a", None)

        assert service._subscriptions_by_entity_id["sensor.a"] == {"req-1", "req-2"}

    def test_subscribe_no_identity_binding_raises(self) -> None:
        """Subscribe with unknown request_id (no identity) raises."""
        service, _, _ = _make_service(oidc_enabled=False)

        with pytest.raises(AuthorizationException, match="No identity binding"):
            service.subscribe("unknown-req", "sensor.a", None)

    def test_subscribe_mismatched_subject_raises(self) -> None:
        """Subscribe with mismatched OIDC subject raises."""
        service, _, mock_auth = _make_service(oidc_enabled=True)
        mock_auth.validate_token.return_value = AuthContext(
            subject="user-A", email=None, name=None, roles=set()
        )
        service.bind_identity("req-1", {"Authorization": "Bearer token"})

        with pytest.raises(AuthorizationException, match="Identity mismatch"):
            service.subscribe("req-1", "sensor.a", "user-B")

    def test_subscribe_with_matching_oidc_subject_succeeds(self) -> None:
        """Subscribe with matching OIDC subject succeeds."""
        service, _, mock_auth = _make_service(oidc_enabled=True)
        mock_auth.validate_token.return_value = AuthContext(
            subject="user-A", email=None, name=None, roles=set()
        )
        service.bind_identity("req-1", {"Authorization": "Bearer token"})

        service.subscribe("req-1", "sensor.a", "user-A")

        assert "sensor.a" in service._subscriptions_by_request_id["req-1"]

    def test_unsubscribe_success(self) -> None:
        """Unsubscribe removes from both maps."""
        service, _, _ = _make_service(oidc_enabled=False)
        service.bind_identity("req-1", {})
        service.subscribe("req-1", "sensor.a", None)

        service.unsubscribe("req-1", "sensor.a", None)

        assert "req-1" not in service._subscriptions_by_request_id
        assert "sensor.a" not in service._subscriptions_by_entity_id

    def test_unsubscribe_nonexistent_raises(self) -> None:
        """Unsubscribe for a non-existent subscription raises."""
        service, _, _ = _make_service(oidc_enabled=False)
        service.bind_identity("req-1", {})

        with pytest.raises(RecordNotFoundException, match="Subscription"):
            service.unsubscribe("req-1", "sensor.a", None)

    def test_unsubscribe_keeps_other_subscriptions(self) -> None:
        """Unsubscribing one device keeps the other subscriptions intact."""
        service, _, _ = _make_service(oidc_enabled=False)
        service.bind_identity("req-1", {})
        service.subscribe("req-1", "sensor.a", None)
        service.subscribe("req-1", "sensor.b", None)

        service.unsubscribe("req-1", "sensor.a", None)

        assert service._subscriptions_by_request_id["req-1"] == {"sensor.b"}
        assert "sensor.a" not in service._subscriptions_by_entity_id


class TestLogForwarding:
    """Tests for log message forwarding via SSE."""

    def test_forward_logs_to_subscribers(self) -> None:
        """Matching logs are sent to subscribed request_ids."""
        service, mock_sse, _ = _make_service(oidc_enabled=False)
        mock_sse.send_event.return_value = True
        service.bind_identity("req-1", {})
        service.subscribe("req-1", "sensor.a", None)

        documents = [
            {"entity_id": "sensor.a", "message": "Log 1", "level": "INFO"},
            {"entity_id": "sensor.a", "message": "Log 2", "level": "ERROR"},
        ]
        service.forward_logs(documents)

        mock_sse.send_event.assert_called_once()
        call_args = mock_sse.send_event.call_args
        assert call_args[0][0] == "req-1"  # request_id
        assert call_args[0][1]["device_entity_id"] == "sensor.a"
        assert len(call_args[0][1]["logs"]) == 2
        assert call_args[1]["event_name"] == "device-logs"

    def test_forward_logs_no_match(self) -> None:
        """Non-matching entity_id results in no SSE events."""
        service, mock_sse, _ = _make_service(oidc_enabled=False)
        service.bind_identity("req-1", {})
        service.subscribe("req-1", "sensor.a", None)

        documents = [{"entity_id": "sensor.b", "message": "Log 1"}]
        service.forward_logs(documents)

        mock_sse.send_event.assert_not_called()

    def test_forward_logs_no_subscriptions(self) -> None:
        """When no subscriptions exist, forward_logs is a fast no-op."""
        service, mock_sse, _ = _make_service(oidc_enabled=False)

        documents = [{"entity_id": "sensor.a", "message": "Log 1"}]
        service.forward_logs(documents)

        mock_sse.send_event.assert_not_called()

    def test_forward_logs_skips_docs_without_entity_id(self) -> None:
        """Documents missing entity_id field are skipped."""
        service, mock_sse, _ = _make_service(oidc_enabled=False)
        mock_sse.send_event.return_value = True
        service.bind_identity("req-1", {})
        service.subscribe("req-1", "sensor.a", None)

        documents = [
            {"message": "No entity_id"},
            {"entity_id": "sensor.a", "message": "Has entity_id"},
        ]
        service.forward_logs(documents)

        mock_sse.send_event.assert_called_once()
        call_args = mock_sse.send_event.call_args
        assert len(call_args[0][1]["logs"]) == 1

    def test_forward_logs_multiple_subscribers(self) -> None:
        """Logs for a device are sent to all subscribed connections."""
        service, mock_sse, _ = _make_service(oidc_enabled=False)
        mock_sse.send_event.return_value = True
        service.bind_identity("req-1", {})
        service.bind_identity("req-2", {})
        service.subscribe("req-1", "sensor.a", None)
        service.subscribe("req-2", "sensor.a", None)

        documents = [{"entity_id": "sensor.a", "message": "Log 1"}]
        service.forward_logs(documents)

        assert mock_sse.send_event.call_count == 2
        sent_request_ids = {
            call[0][0] for call in mock_sse.send_event.call_args_list
        }
        assert sent_request_ids == {"req-1", "req-2"}

    def test_forward_logs_groups_by_entity(self) -> None:
        """Documents are grouped by entity_id for batched delivery."""
        service, mock_sse, _ = _make_service(oidc_enabled=False)
        mock_sse.send_event.return_value = True
        service.bind_identity("req-1", {})
        service.bind_identity("req-2", {})
        service.subscribe("req-1", "sensor.a", None)
        service.subscribe("req-2", "sensor.b", None)

        documents = [
            {"entity_id": "sensor.a", "message": "Log A"},
            {"entity_id": "sensor.b", "message": "Log B"},
        ]
        service.forward_logs(documents)

        assert mock_sse.send_event.call_count == 2

    def test_forward_logs_during_shutdown_is_noop(self) -> None:
        """During shutdown, forward_logs does nothing."""
        lifecycle = TestLifecycleCoordinator()
        service, mock_sse, _ = _make_service(
            oidc_enabled=False, lifecycle=lifecycle
        )
        service.bind_identity("req-1", {})
        service.subscribe("req-1", "sensor.a", None)

        # Trigger shutdown
        lifecycle.simulate_shutdown()

        documents = [{"entity_id": "sensor.a", "message": "Log 1"}]
        service.forward_logs(documents)

        mock_sse.send_event.assert_not_called()


class TestRotationNudge:
    """Tests for rotation nudge broadcast."""

    def test_broadcast_rotation_nudge(self) -> None:
        """Broadcast sends rotation-updated event with empty payload."""
        service, mock_sse, _ = _make_service(oidc_enabled=False)
        mock_sse.send_event.return_value = True

        result = service.broadcast_rotation_nudge(source="web")

        assert result is True
        mock_sse.send_event.assert_called_once_with(
            None, {}, event_name="rotation-updated", service_type="rotation"
        )

    def test_broadcast_rotation_nudge_no_connections(self) -> None:
        """Broadcast returns False when no connections exist."""
        service, mock_sse, _ = _make_service(oidc_enabled=False)
        mock_sse.send_event.return_value = False

        result = service.broadcast_rotation_nudge(source="cronjob")

        assert result is False

    def test_broadcast_rotation_nudge_during_shutdown(self) -> None:
        """During shutdown, broadcast returns False."""
        lifecycle = TestLifecycleCoordinator()
        service, mock_sse, _ = _make_service(
            oidc_enabled=False, lifecycle=lifecycle
        )

        lifecycle.simulate_shutdown()

        result = service.broadcast_rotation_nudge()

        assert result is False
        mock_sse.send_event.assert_not_called()


class TestDisconnectCleanup:
    """Tests for SSE disconnect cleanup."""

    def test_disconnect_removes_all_subscriptions(self) -> None:
        """Disconnect removes all subscriptions for a request_id."""
        service, mock_sse, _ = _make_service(oidc_enabled=False)
        service.bind_identity("req-1", {})
        service.subscribe("req-1", "sensor.a", None)
        service.subscribe("req-1", "sensor.b", None)

        service._on_disconnect_callback("req-1")

        assert "req-1" not in service._subscriptions_by_request_id
        assert "sensor.a" not in service._subscriptions_by_entity_id
        assert "sensor.b" not in service._subscriptions_by_entity_id

    def test_disconnect_removes_identity_mapping(self) -> None:
        """Disconnect removes the identity mapping for the request_id."""
        service, _, _ = _make_service(oidc_enabled=False)
        service.bind_identity("req-1", {})

        service._on_disconnect_callback("req-1")

        assert "req-1" not in service._identity_map

    def test_disconnect_preserves_other_connections(self) -> None:
        """Disconnect for one connection preserves other connections' subscriptions."""
        service, _, _ = _make_service(oidc_enabled=False)
        service.bind_identity("req-1", {})
        service.bind_identity("req-2", {})
        service.subscribe("req-1", "sensor.a", None)
        service.subscribe("req-2", "sensor.a", None)

        service._on_disconnect_callback("req-1")

        # req-2 should still be subscribed
        assert "req-2" in service._subscriptions_by_entity_id["sensor.a"]
        assert "req-2" in service._identity_map

    def test_disconnect_no_subscriptions_is_safe(self) -> None:
        """Disconnect for a request_id with no subscriptions is safe."""
        service, _, _ = _make_service(oidc_enabled=False)
        service.bind_identity("req-1", {})

        # Should not raise
        service._on_disconnect_callback("req-1")

        assert "req-1" not in service._identity_map

    def test_disconnect_unknown_request_id_is_safe(self) -> None:
        """Disconnect for an unknown request_id is safe."""
        service, _, _ = _make_service(oidc_enabled=False)

        # Should not raise
        service._on_disconnect_callback("unknown-req")


class TestLifecycleShutdown:
    """Tests for lifecycle coordinator integration."""

    def test_prepare_shutdown_clears_all_state(self) -> None:
        """PREPARE_SHUTDOWN clears all maps and sets shutdown flag."""
        lifecycle = TestLifecycleCoordinator()
        service, _, _ = _make_service(oidc_enabled=False, lifecycle=lifecycle)

        service.bind_identity("req-1", {})
        service.subscribe("req-1", "sensor.a", None)

        lifecycle.simulate_shutdown()

        assert len(service._subscriptions_by_request_id) == 0
        assert len(service._subscriptions_by_entity_id) == 0
        assert len(service._identity_map) == 0
        assert service._is_shutting_down is True

    def test_subscribe_after_shutdown_does_not_crash(self) -> None:
        """After shutdown, subscribe still works (identity was cleared)."""
        lifecycle = TestLifecycleCoordinator()
        service, _, _ = _make_service(oidc_enabled=False, lifecycle=lifecycle)

        service.bind_identity("req-1", {})
        lifecycle.simulate_shutdown()

        # Identity was cleared, so this should raise about no identity
        with pytest.raises(AuthorizationException, match="No identity binding"):
            service.subscribe("req-1", "sensor.a", None)
