"""Tests for SSEConnectionManager: disconnect observer pattern and identity binding."""

from unittest.mock import MagicMock

from app.services.sse_connection_manager import SSEConnectionManager


class TestRegisterOnDisconnect:
    """Tests for the register_on_disconnect observer pattern."""

    def test_disconnect_callback_invoked_on_valid_disconnect(self) -> None:
        """Given a registered on_disconnect callback, when on_disconnect is
        called with a valid token, then the callback is invoked with the request_id."""
        manager = SSEConnectionManager(gateway_url="http://localhost:3001")
        callback = MagicMock()
        manager.register_on_disconnect(callback)

        # Establish a connection first
        manager.on_connect("req-1", "token-abc", "http://example.com")

        # Disconnect
        manager.on_disconnect("token-abc")

        callback.assert_called_once_with("req-1")

    def test_disconnect_callback_not_invoked_for_stale_token(self) -> None:
        """Given a registered on_disconnect callback, when on_disconnect is
        called with a stale/unknown token, then the callback is NOT invoked."""
        manager = SSEConnectionManager(gateway_url="http://localhost:3001")
        callback = MagicMock()
        manager.register_on_disconnect(callback)

        # No connection registered for this token
        manager.on_disconnect("unknown-token")

        callback.assert_not_called()

    def test_disconnect_callback_not_invoked_for_replaced_connection(self) -> None:
        """Given a registered on_disconnect callback, when on_disconnect is
        called with a mismatched token (connection was replaced), then the
        callback is NOT invoked."""
        manager = SSEConnectionManager(gateway_url="http://localhost:3001")
        callback = MagicMock()
        manager.register_on_disconnect(callback)

        # Establish connection, then replace it with a new token
        manager.on_connect("req-1", "old-token", "http://example.com")
        manager.on_connect("req-1", "new-token", "http://example.com")

        # Disconnect with old (stale) token
        manager.on_disconnect("old-token")

        callback.assert_not_called()

    def test_multiple_disconnect_callbacks_all_invoked(self) -> None:
        """Given multiple registered on_disconnect callbacks, when disconnect
        occurs, then all callbacks are invoked."""
        manager = SSEConnectionManager(gateway_url="http://localhost:3001")
        callback1 = MagicMock()
        callback2 = MagicMock()
        manager.register_on_disconnect(callback1)
        manager.register_on_disconnect(callback2)

        manager.on_connect("req-1", "token-abc", "http://example.com")
        manager.on_disconnect("token-abc")

        callback1.assert_called_once_with("req-1")
        callback2.assert_called_once_with("req-1")

    def test_callback_exception_does_not_block_other_callbacks(self) -> None:
        """Given a callback that raises an exception, when disconnect occurs,
        then other callbacks still execute."""
        manager = SSEConnectionManager(gateway_url="http://localhost:3001")
        failing_callback = MagicMock(side_effect=RuntimeError("test error"))
        success_callback = MagicMock()
        manager.register_on_disconnect(failing_callback)
        manager.register_on_disconnect(success_callback)

        manager.on_connect("req-1", "token-abc", "http://example.com")
        manager.on_disconnect("token-abc")

        failing_callback.assert_called_once_with("req-1")
        success_callback.assert_called_once_with("req-1")

    def test_disconnect_removes_connection_mappings(self) -> None:
        """Verify that on_disconnect correctly removes both forward and reverse
        mappings so the connection is fully cleaned up."""
        manager = SSEConnectionManager(gateway_url="http://localhost:3001")

        manager.on_connect("req-1", "token-abc", "http://example.com")
        assert manager.has_connection("req-1") is True

        manager.on_disconnect("token-abc")
        assert manager.has_connection("req-1") is False

    def test_connect_callback_still_works_with_disconnect_registered(self) -> None:
        """Verify that registering disconnect callbacks does not interfere
        with connect callbacks."""
        manager = SSEConnectionManager(gateway_url="http://localhost:3001")
        connect_cb = MagicMock()
        disconnect_cb = MagicMock()
        manager.register_on_connect(connect_cb)
        manager.register_on_disconnect(disconnect_cb)

        manager.on_connect("req-1", "token-abc", "http://example.com")

        connect_cb.assert_called_once_with("req-1")
        disconnect_cb.assert_not_called()

        manager.on_disconnect("token-abc")

        disconnect_cb.assert_called_once_with("req-1")


class TestIdentityBinding:
    """Tests for bind_identity and get_connection_info."""

    def test_bind_identity_stores_subject(self) -> None:
        """bind_identity stores the subject for an active connection."""
        manager = SSEConnectionManager(gateway_url="http://localhost:3001")
        manager.on_connect("req-1", "token-abc", "http://example.com")

        manager.bind_identity("req-1", "user-123")

        info = manager.get_connection_info("req-1")
        assert info is not None
        assert info.subject == "user-123"

    def test_bind_identity_no_connection_is_noop(self) -> None:
        """bind_identity for a non-existent connection does not store anything."""
        manager = SSEConnectionManager(gateway_url="http://localhost:3001")

        manager.bind_identity("req-unknown", "user-123")

        assert manager.get_connection_info("req-unknown") is None

    def test_get_connection_info_without_identity(self) -> None:
        """get_connection_info returns None subject when identity not bound."""
        manager = SSEConnectionManager(gateway_url="http://localhost:3001")
        manager.on_connect("req-1", "token-abc", "http://example.com")

        info = manager.get_connection_info("req-1")
        assert info is not None
        assert info.request_id == "req-1"
        assert info.subject is None

    def test_get_connection_info_not_connected(self) -> None:
        """get_connection_info returns None for unknown request_id."""
        manager = SSEConnectionManager(gateway_url="http://localhost:3001")

        assert manager.get_connection_info("req-unknown") is None

    def test_disconnect_clears_identity(self) -> None:
        """on_disconnect removes the identity mapping along with connection."""
        manager = SSEConnectionManager(gateway_url="http://localhost:3001")
        manager.on_connect("req-1", "token-abc", "http://example.com")
        manager.bind_identity("req-1", "user-123")

        manager.on_disconnect("token-abc")

        assert manager.get_connection_info("req-1") is None
        assert "req-1" not in manager._identity_map

    def test_bind_identity_overwrite(self) -> None:
        """Binding identity twice overwrites the previous subject."""
        manager = SSEConnectionManager(gateway_url="http://localhost:3001")
        manager.on_connect("req-1", "token-abc", "http://example.com")

        manager.bind_identity("req-1", "user-A")
        manager.bind_identity("req-1", "user-B")

        info = manager.get_connection_info("req-1")
        assert info is not None
        assert info.subject == "user-B"
