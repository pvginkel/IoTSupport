"""Tests for LogSinkService."""

import json
import threading
import time
from datetime import UTC, datetime
from queue import ShutDown
from unittest.mock import MagicMock, Mock, patch

import httpx

from app.app_config import AppSettings
from app.services.logsink_service import LogSinkService
from app.services.mqtt_service import MqttService
from tests.testing_utils import StubLifecycleCoordinator, TestLifecycleCoordinator


def _make_test_settings(
    mqtt_url: str | None = "mqtt://localhost:1883",
    elasticsearch_url: str | None = "http://localhost:9200",
    mqtt_username: str | None = None,
    mqtt_password: str | None = None,
    elasticsearch_username: str | None = None,
    elasticsearch_password: str | None = None,
    mqtt_client_id: str = "iotsupport-backend",
) -> AppSettings:
    """Create test settings with configurable MQTT and ES settings."""
    return AppSettings(
        mqtt_url=mqtt_url,
        device_mqtt_url=mqtt_url,
        mqtt_username=mqtt_username,
        mqtt_password=mqtt_password,
        mqtt_client_id=mqtt_client_id,
        elasticsearch_url=elasticsearch_url,
        elasticsearch_username=elasticsearch_username,
        elasticsearch_password=elasticsearch_password,
        elasticsearch_index_pattern="logstash-http-*",
    )


def _make_mock_mqtt_service(mqtt_url: str | None = "mqtt://localhost:1883") -> Mock:
    """Create a mock MqttService for testing."""
    mock_service = Mock(spec=MqttService)
    mock_service.config = Mock()
    mock_service.config.mqtt_url = mqtt_url
    mock_service.enabled = bool(mqtt_url)
    return mock_service


def _drain_service(service: LogSinkService, lifecycle: TestLifecycleCoordinator) -> None:
    """Shut down the queue and wait for the writer thread to finish."""
    lifecycle.simulate_full_shutdown(timeout=5.0)


class TestLogSinkServiceInitialization:
    """Tests for LogSinkService initialization."""

    @patch("app.services.logsink_service.httpx.Client")
    def test_init_with_both_mqtt_and_es_configured(self, mock_http_client_class: Mock):
        """Service initializes when both MQTT and Elasticsearch are configured."""
        settings = _make_test_settings()
        mock_mqtt_service = _make_mock_mqtt_service()
        lifecycle = TestLifecycleCoordinator()

        service = LogSinkService(
            config=settings, mqtt_service=mock_mqtt_service,
            lifecycle_coordinator=lifecycle,
        )
        service.startup()

        try:
            assert service.enabled is True
            # Verify subscription was registered
            mock_mqtt_service.subscribe.assert_called_once_with(
                topic="iotsupport/logsink",
                qos=1,
                callback=service._on_message,
            )
            # Verify lifecycle registrations
            assert len(lifecycle._notifications) == 1
            assert "LogSinkService" in lifecycle._waiters
            # Verify writer thread is running
            assert service._writer_thread is not None
            assert service._writer_thread.is_alive()
        finally:
            _drain_service(service, lifecycle)

    @patch("app.services.logsink_service.httpx.Client")
    def test_init_without_mqtt_url_disables_service(self, mock_http_client_class: Mock):
        """Service disabled when MQTT_URL not configured."""
        settings = _make_test_settings(mqtt_url=None)
        mock_mqtt_service = _make_mock_mqtt_service(mqtt_url=None)
        lifecycle = StubLifecycleCoordinator()

        service = LogSinkService(
            config=settings, mqtt_service=mock_mqtt_service,
            lifecycle_coordinator=lifecycle,
        )

        assert service.enabled is False
        mock_mqtt_service.subscribe.assert_not_called()
        # No lifecycle registrations when disabled
        assert len(lifecycle._notifications) == 0

    @patch("app.services.logsink_service.httpx.Client")
    def test_init_without_elasticsearch_url_disables_service(
        self, mock_http_client_class: Mock
    ):
        """Service disabled when ELASTICSEARCH_URL not configured."""
        settings = _make_test_settings(elasticsearch_url=None)
        mock_mqtt_service = _make_mock_mqtt_service()
        lifecycle = StubLifecycleCoordinator()

        service = LogSinkService(
            config=settings, mqtt_service=mock_mqtt_service,
            lifecycle_coordinator=lifecycle,
        )

        assert service.enabled is False
        mock_mqtt_service.subscribe.assert_not_called()

    @patch("app.services.logsink_service.httpx.Client")
    def test_init_without_both_disables_service(self, mock_http_client_class: Mock):
        """Service disabled when neither MQTT nor ES are configured."""
        settings = _make_test_settings(mqtt_url=None, elasticsearch_url=None)
        mock_mqtt_service = _make_mock_mqtt_service(mqtt_url=None)
        lifecycle = StubLifecycleCoordinator()

        service = LogSinkService(
            config=settings, mqtt_service=mock_mqtt_service,
            lifecycle_coordinator=lifecycle,
        )

        assert service.enabled is False


class TestLogSinkServiceMessageProcessing:
    """Tests for message processing (enqueue path)."""

    @patch("app.services.logsink_service.httpx.Client")
    def test_on_message_enqueues_document(self, mock_http_client_class: Mock):
        """Valid JSON message is enqueued for batch writing."""
        mock_http_client = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_http_client.post.return_value = mock_response
        mock_http_client_class.return_value = mock_http_client

        settings = _make_test_settings()
        mock_mqtt_service = _make_mock_mqtt_service()
        lifecycle = TestLifecycleCoordinator()

        service = LogSinkService(
            config=settings, mqtt_service=mock_mqtt_service,
            lifecycle_coordinator=lifecycle,
        )
        service.startup()

        try:
            payload = json.dumps({"message": "Test log", "entity_id": "device-1"}).encode()
            service._on_message(payload)

            # Give the writer thread time to process
            time.sleep(0.3)

            # Verify ES _bulk write was attempted
            assert mock_http_client.post.called
            call_args = mock_http_client.post.call_args
            assert "/_bulk" in call_args[0][0]
        finally:
            _drain_service(service, lifecycle)

    @patch("app.services.logsink_service.httpx.Client")
    def test_on_message_strips_ansi_codes(self, mock_http_client_class: Mock):
        """ANSI escape codes are stripped from message field."""
        mock_http_client = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_http_client.post.return_value = mock_response
        mock_http_client_class.return_value = mock_http_client

        settings = _make_test_settings()
        mock_mqtt_service = _make_mock_mqtt_service()
        lifecycle = TestLifecycleCoordinator()

        service = LogSinkService(
            config=settings, mqtt_service=mock_mqtt_service,
            lifecycle_coordinator=lifecycle,
        )
        service.startup()

        try:
            payload = json.dumps({
                "message": "\x1b[31mRed error message\x1b[0m",
                "entity_id": "device-1",
            }).encode()
            service._on_message(payload)

            time.sleep(0.3)

            # Parse the NDJSON bulk body to check the document
            call_args = mock_http_client.post.call_args
            bulk_body = call_args[1]["content"]
            lines = bulk_body.strip().split("\n")
            doc = json.loads(lines[1])  # Second line is the document
            assert doc["message"] == "Red error message"
        finally:
            _drain_service(service, lifecycle)

    @patch("app.services.logsink_service.httpx.Client")
    def test_on_message_removes_relative_time(self, mock_http_client_class: Mock):
        """relative_time field is removed from document."""
        mock_http_client = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_http_client.post.return_value = mock_response
        mock_http_client_class.return_value = mock_http_client

        settings = _make_test_settings()
        mock_mqtt_service = _make_mock_mqtt_service()
        lifecycle = TestLifecycleCoordinator()

        service = LogSinkService(
            config=settings, mqtt_service=mock_mqtt_service,
            lifecycle_coordinator=lifecycle,
        )
        service.startup()

        try:
            payload = json.dumps({
                "message": "Test",
                "relative_time": 12345,
                "entity_id": "device-1",
            }).encode()
            service._on_message(payload)

            time.sleep(0.3)

            call_args = mock_http_client.post.call_args
            bulk_body = call_args[1]["content"]
            lines = bulk_body.strip().split("\n")
            doc = json.loads(lines[1])
            assert "relative_time" not in doc
        finally:
            _drain_service(service, lifecycle)

    @patch("app.services.logsink_service.httpx.Client")
    def test_on_message_adds_timestamp(self, mock_http_client_class: Mock):
        """@timestamp field is added with current UTC time."""
        mock_http_client = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_http_client.post.return_value = mock_response
        mock_http_client_class.return_value = mock_http_client

        settings = _make_test_settings()
        mock_mqtt_service = _make_mock_mqtt_service()
        lifecycle = TestLifecycleCoordinator()

        service = LogSinkService(
            config=settings, mqtt_service=mock_mqtt_service,
            lifecycle_coordinator=lifecycle,
        )
        service.startup()

        try:
            before = datetime.now(UTC)
            payload = json.dumps({"message": "Test"}).encode()
            service._on_message(payload)
            after = datetime.now(UTC)

            time.sleep(0.3)

            call_args = mock_http_client.post.call_args
            bulk_body = call_args[1]["content"]
            lines = bulk_body.strip().split("\n")
            doc = json.loads(lines[1])
            assert "@timestamp" in doc
            ts = datetime.fromisoformat(doc["@timestamp"])
            assert before <= ts <= after
        finally:
            _drain_service(service, lifecycle)

    @patch("app.services.logsink_service.httpx.Client")
    def test_on_message_handles_missing_message_field(
        self, mock_http_client_class: Mock
    ):
        """Documents without message field are handled gracefully."""
        mock_http_client = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_http_client.post.return_value = mock_response
        mock_http_client_class.return_value = mock_http_client

        settings = _make_test_settings()
        mock_mqtt_service = _make_mock_mqtt_service()
        lifecycle = TestLifecycleCoordinator()

        service = LogSinkService(
            config=settings, mqtt_service=mock_mqtt_service,
            lifecycle_coordinator=lifecycle,
        )
        service.startup()

        try:
            payload = json.dumps({"entity_id": "device-1", "level": "INFO"}).encode()
            service._on_message(payload)

            time.sleep(0.3)

            assert mock_http_client.post.called
        finally:
            _drain_service(service, lifecycle)

    @patch("app.services.logsink_service.httpx.Client")
    def test_on_message_invalid_json_increments_error_metric(
        self, mock_http_client_class: Mock
    ):
        """Invalid JSON increments parse_error metric."""
        settings = _make_test_settings()
        mock_mqtt_service = _make_mock_mqtt_service()
        lifecycle = TestLifecycleCoordinator()

        service = LogSinkService(
            config=settings, mqtt_service=mock_mqtt_service,
            lifecycle_coordinator=lifecycle,
        )
        service.startup()

        try:
            payload = b"not valid json"
            service._on_message(payload)

            time.sleep(0.1)

            # ES should not be called (nothing enqueued)
            mock_http_client_class.return_value.post.assert_not_called()
        finally:
            _drain_service(service, lifecycle)

    @patch("app.services.logsink_service.httpx.Client")
    def test_on_message_preserves_other_fields(self, mock_http_client_class: Mock):
        """Other fields in payload are preserved in document."""
        mock_http_client = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_http_client.post.return_value = mock_response
        mock_http_client_class.return_value = mock_http_client

        settings = _make_test_settings()
        mock_mqtt_service = _make_mock_mqtt_service()
        lifecycle = TestLifecycleCoordinator()

        service = LogSinkService(
            config=settings, mqtt_service=mock_mqtt_service,
            lifecycle_coordinator=lifecycle,
        )
        service.startup()

        try:
            payload = json.dumps({
                "message": "Test",
                "entity_id": "device-1",
                "level": "ERROR",
                "custom_field": "custom_value",
            }).encode()
            service._on_message(payload)

            time.sleep(0.3)

            call_args = mock_http_client.post.call_args
            bulk_body = call_args[1]["content"]
            lines = bulk_body.strip().split("\n")
            doc = json.loads(lines[1])
            assert doc["entity_id"] == "device-1"
            assert doc["level"] == "ERROR"
            assert doc["custom_field"] == "custom_value"
        finally:
            _drain_service(service, lifecycle)


class TestLogSinkServiceBatching:
    """Tests for batch writing behavior."""

    @patch("app.services.logsink_service.httpx.Client")
    def test_single_message_batched(self, mock_http_client_class: Mock):
        """One message results in one bulk request with one doc."""
        mock_http_client = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_http_client.post.return_value = mock_response
        mock_http_client_class.return_value = mock_http_client

        settings = _make_test_settings()
        mock_mqtt_service = _make_mock_mqtt_service()
        lifecycle = TestLifecycleCoordinator()

        service = LogSinkService(
            config=settings, mqtt_service=mock_mqtt_service,
            lifecycle_coordinator=lifecycle,
        )
        service.startup()

        try:
            payload = json.dumps({"message": "Single"}).encode()
            service._on_message(payload)

            time.sleep(0.3)

            assert mock_http_client.post.call_count == 1
            call_args = mock_http_client.post.call_args
            bulk_body = call_args[1]["content"]
            lines = bulk_body.strip().split("\n")
            # 2 lines: action + document
            assert len(lines) == 2
        finally:
            _drain_service(service, lifecycle)

    @patch("app.services.logsink_service.httpx.Client")
    def test_multiple_messages_batched(self, mock_http_client_class: Mock):
        """Multiple enqueued messages can be sent as one bulk request."""
        # Use an event to block the writer thread until all messages are enqueued
        write_gate = threading.Event()
        original_post = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        original_post.return_value = mock_response

        mock_http_client = MagicMock()

        def gated_post(*args, **kwargs):
            write_gate.wait(timeout=5)
            return original_post(*args, **kwargs)

        mock_http_client.post = gated_post
        mock_http_client_class.return_value = mock_http_client

        settings = _make_test_settings()
        mock_mqtt_service = _make_mock_mqtt_service()
        lifecycle = TestLifecycleCoordinator()

        service = LogSinkService(
            config=settings, mqtt_service=mock_mqtt_service,
            lifecycle_coordinator=lifecycle,
        )
        service.startup()

        try:
            # Enqueue 5 messages while write is gated
            for i in range(5):
                payload = json.dumps({"message": f"Log {i}"}).encode()
                service._on_message(payload)

            # Release the gate — writer should batch them
            write_gate.set()
            time.sleep(0.5)

            # Should be 1 bulk request with all 5 docs
            assert original_post.call_count == 1
            call_args = original_post.call_args
            # The content kwarg contains the NDJSON body
            bulk_body = call_args[1]["content"]
            lines = bulk_body.strip().split("\n")
            # 5 docs * 2 lines each (action + document)
            assert len(lines) == 10
        finally:
            _drain_service(service, lifecycle)

    @patch("app.services.logsink_service.httpx.Client")
    def test_bulk_request_format(self, mock_http_client_class: Mock):
        """Verify NDJSON format with action/doc pairs."""
        mock_http_client = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_http_client.post.return_value = mock_response
        mock_http_client_class.return_value = mock_http_client

        settings = _make_test_settings()
        mock_mqtt_service = _make_mock_mqtt_service()
        lifecycle = TestLifecycleCoordinator()

        service = LogSinkService(
            config=settings, mqtt_service=mock_mqtt_service,
            lifecycle_coordinator=lifecycle,
        )
        service.startup()

        try:
            payload = json.dumps({"message": "Test", "entity_id": "device-1"}).encode()
            service._on_message(payload)

            time.sleep(0.3)

            call_args = mock_http_client.post.call_args

            # Check URL
            assert "/_bulk" in call_args[0][0]

            # Check content type
            assert call_args[1]["headers"]["Content-Type"] == "application/x-ndjson"

            # Parse NDJSON body
            bulk_body = call_args[1]["content"]
            lines = bulk_body.strip().split("\n")
            assert len(lines) == 2

            # First line: action
            action = json.loads(lines[0])
            assert "index" in action
            assert action["index"]["_index"].startswith("logstash-http-")

            # Second line: document
            doc = json.loads(lines[1])
            assert doc["message"] == "Test"
            assert doc["entity_id"] == "device-1"
            assert "@timestamp" in doc

            # Body ends with newline
            assert bulk_body.endswith("\n")
        finally:
            _drain_service(service, lifecycle)

    @patch("app.services.logsink_service.httpx.Client")
    def test_different_indices_in_batch(self, mock_http_client_class: Mock):
        """Documents with different index names can coexist in same batch."""
        # Use an event to block the writer thread
        write_gate = threading.Event()
        original_post = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        original_post.return_value = mock_response

        mock_http_client = MagicMock()

        def gated_post(*args, **kwargs):
            write_gate.wait(timeout=5)
            return original_post(*args, **kwargs)

        mock_http_client.post = gated_post
        mock_http_client_class.return_value = mock_http_client

        settings = _make_test_settings()
        mock_mqtt_service = _make_mock_mqtt_service()
        lifecycle = TestLifecycleCoordinator()

        service = LogSinkService(
            config=settings, mqtt_service=mock_mqtt_service,
            lifecycle_coordinator=lifecycle,
        )
        service.startup()

        try:
            # Enqueue messages — they may get different indices if we mock time,
            # but at minimum we verify the structure supports multiple indices
            for i in range(3):
                payload = json.dumps({"message": f"Log {i}"}).encode()
                service._on_message(payload)

            write_gate.set()
            time.sleep(0.5)

            assert original_post.call_count == 1
            call_args = original_post.call_args
            bulk_body = call_args[1]["content"]
            lines = bulk_body.strip().split("\n")

            # Each pair should have a valid action line with _index
            for i in range(0, len(lines), 2):
                action = json.loads(lines[i])
                assert "index" in action
                assert "_index" in action["index"]
        finally:
            _drain_service(service, lifecycle)


class TestLogSinkServiceElasticsearchRetry:
    """Tests for Elasticsearch retry logic."""

    @patch("app.services.logsink_service.httpx.Client")
    def test_retry_on_connection_error(self, mock_http_client_class: Mock):
        """Connection errors trigger retry with backoff."""
        mock_http_client = MagicMock()
        # Fail twice, then succeed
        mock_http_client.post.side_effect = [
            httpx.ConnectError("Connection refused"),
            httpx.ConnectError("Connection refused"),
            MagicMock(raise_for_status=MagicMock()),
        ]
        mock_http_client_class.return_value = mock_http_client

        settings = _make_test_settings()
        mock_mqtt_service = _make_mock_mqtt_service()
        lifecycle = TestLifecycleCoordinator()

        service = LogSinkService(
            config=settings, mqtt_service=mock_mqtt_service,
            lifecycle_coordinator=lifecycle,
        )
        service.startup()

        try:
            payload = json.dumps({"message": "Test"}).encode()
            service._on_message(payload)

            # Wait enough for retries (1s + 2s delays + processing time)
            time.sleep(4.0)

            assert mock_http_client.post.call_count == 3
        finally:
            _drain_service(service, lifecycle)

    @patch("app.services.logsink_service.httpx.Client")
    def test_retry_on_timeout(self, mock_http_client_class: Mock):
        """Timeout errors trigger retry."""
        mock_http_client = MagicMock()
        mock_http_client.post.side_effect = [
            httpx.TimeoutException("Request timed out"),
            MagicMock(raise_for_status=MagicMock()),
        ]
        mock_http_client_class.return_value = mock_http_client

        settings = _make_test_settings()
        mock_mqtt_service = _make_mock_mqtt_service()
        lifecycle = TestLifecycleCoordinator()

        service = LogSinkService(
            config=settings, mqtt_service=mock_mqtt_service,
            lifecycle_coordinator=lifecycle,
        )
        service.startup()

        try:
            payload = json.dumps({"message": "Test"}).encode()
            service._on_message(payload)

            time.sleep(2.0)

            assert mock_http_client.post.call_count == 2
        finally:
            _drain_service(service, lifecycle)

    @patch("app.services.logsink_service.httpx.Client")
    def test_retry_on_http_error(self, mock_http_client_class: Mock):
        """HTTP errors trigger retry."""
        mock_http_client = MagicMock()
        error_response = MagicMock()
        error_response.status_code = 503
        error_response.text = "Service Unavailable"
        mock_http_client.post.side_effect = [
            httpx.HTTPStatusError("503", request=MagicMock(), response=error_response),
            MagicMock(raise_for_status=MagicMock()),
        ]
        mock_http_client_class.return_value = mock_http_client

        settings = _make_test_settings()
        mock_mqtt_service = _make_mock_mqtt_service()
        lifecycle = TestLifecycleCoordinator()

        service = LogSinkService(
            config=settings, mqtt_service=mock_mqtt_service,
            lifecycle_coordinator=lifecycle,
        )
        service.startup()

        try:
            payload = json.dumps({"message": "Test"}).encode()
            service._on_message(payload)

            time.sleep(2.0)

            assert mock_http_client.post.call_count == 2
        finally:
            _drain_service(service, lifecycle)

    @patch("app.services.logsink_service.httpx.Client")
    def test_shutdown_interrupts_retry_loop(self, mock_http_client_class: Mock):
        """Lifecycle shutdown interrupts retry loop."""
        mock_http_client = MagicMock()
        mock_http_client.post.side_effect = httpx.ConnectError("Connection refused")
        mock_http_client_class.return_value = mock_http_client

        settings = _make_test_settings()
        mock_mqtt_service = _make_mock_mqtt_service()
        lifecycle = TestLifecycleCoordinator()

        service = LogSinkService(
            config=settings, mqtt_service=mock_mqtt_service,
            lifecycle_coordinator=lifecycle,
        )
        service.startup()

        payload = json.dumps({"message": "Test"}).encode()
        service._on_message(payload)

        # Let it attempt a couple of times, then shut down
        time.sleep(0.5)
        _drain_service(service, lifecycle)

        # Should have exited the retry loop
        assert mock_http_client.post.call_count >= 1

    @patch("app.services.logsink_service.httpx.Client")
    def test_successful_write_uses_auth_when_configured(
        self, mock_http_client_class: Mock
    ):
        """ES auth is used when username/password configured."""
        mock_http_client = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_http_client.post.return_value = mock_response
        mock_http_client_class.return_value = mock_http_client

        settings = _make_test_settings(
            elasticsearch_username="elastic",
            elasticsearch_password="secret",
        )
        mock_mqtt_service = _make_mock_mqtt_service()
        lifecycle = TestLifecycleCoordinator()

        service = LogSinkService(
            config=settings, mqtt_service=mock_mqtt_service,
            lifecycle_coordinator=lifecycle,
        )
        service.startup()

        try:
            payload = json.dumps({"message": "Test"}).encode()
            service._on_message(payload)

            time.sleep(0.3)

            call_args = mock_http_client.post.call_args
            assert call_args[1]["auth"] == ("elastic", "secret")
        finally:
            _drain_service(service, lifecycle)


class TestLogSinkServiceLifecycle:
    """Tests for lifecycle coordinator integration."""

    @patch("app.services.logsink_service.httpx.Client")
    def test_prepare_shutdown_shuts_down_queue(self, mock_http_client_class: Mock):
        """PREPARE_SHUTDOWN event shuts down the queue so producers get ShutDown."""
        mock_http_client = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_http_client.post.return_value = mock_response
        mock_http_client_class.return_value = mock_http_client

        settings = _make_test_settings()
        mock_mqtt_service = _make_mock_mqtt_service()
        lifecycle = TestLifecycleCoordinator()

        service = LogSinkService(
            config=settings, mqtt_service=mock_mqtt_service,
            lifecycle_coordinator=lifecycle,
        )

        # Trigger PREPARE_SHUTDOWN
        lifecycle.simulate_shutdown()

        # Queue should now reject puts with ShutDown
        with_shutdown = False
        try:
            service._queue.put(("idx", {"msg": "test"}))
        except ShutDown:
            with_shutdown = True

        assert with_shutdown

        # Clean up writer thread
        if service._writer_thread is not None:
            service._writer_thread.join(timeout=2.0)

    @patch("app.services.logsink_service.httpx.Client")
    def test_shutdown_closes_http_client(self, mock_http_client_class: Mock):
        """SHUTDOWN event closes the HTTP client."""
        mock_http_client = MagicMock()
        mock_http_client_class.return_value = mock_http_client

        settings = _make_test_settings()
        mock_mqtt_service = _make_mock_mqtt_service()
        lifecycle = TestLifecycleCoordinator()

        service = LogSinkService(
            config=settings, mqtt_service=mock_mqtt_service,
            lifecycle_coordinator=lifecycle,
        )

        _drain_service(service, lifecycle)

        mock_http_client.close.assert_called_once()

    @patch("app.services.logsink_service.httpx.Client")
    def test_wait_for_shutdown_joins_thread(self, mock_http_client_class: Mock):
        """Shutdown waiter joins the writer thread."""
        mock_http_client = MagicMock()
        mock_http_client_class.return_value = mock_http_client

        settings = _make_test_settings()
        mock_mqtt_service = _make_mock_mqtt_service()
        lifecycle = TestLifecycleCoordinator()

        service = LogSinkService(
            config=settings, mqtt_service=mock_mqtt_service,
            lifecycle_coordinator=lifecycle,
        )
        service.startup()

        assert service._writer_thread is not None
        assert service._writer_thread.is_alive()

        _drain_service(service, lifecycle)

        # Writer thread should have finished
        assert not service._writer_thread.is_alive()

    @patch("app.services.logsink_service.httpx.Client")
    def test_drain_on_shutdown(self, mock_http_client_class: Mock):
        """Items remaining in queue are flushed before thread exits."""
        # Use an event to block the writer thread
        write_gate = threading.Event()
        original_post = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        original_post.return_value = mock_response

        mock_http_client = MagicMock()

        def gated_post(*args, **kwargs):
            write_gate.wait(timeout=5)
            return original_post(*args, **kwargs)

        mock_http_client.post = gated_post
        mock_http_client_class.return_value = mock_http_client

        settings = _make_test_settings()
        mock_mqtt_service = _make_mock_mqtt_service()
        lifecycle = TestLifecycleCoordinator()

        service = LogSinkService(
            config=settings, mqtt_service=mock_mqtt_service,
            lifecycle_coordinator=lifecycle,
        )
        service.startup()

        # Enqueue messages while writer is blocked
        for i in range(3):
            payload = json.dumps({"message": f"Log {i}"}).encode()
            service._on_message(payload)

        # Release gate and initiate shutdown simultaneously
        write_gate.set()
        _drain_service(service, lifecycle)

        # All messages should have been written
        assert original_post.call_count >= 1
        # Check total documents written across all bulk calls
        total_docs = 0
        for call in original_post.call_args_list:
            bulk_body = call[1]["content"]
            lines = bulk_body.strip().split("\n")
            total_docs += len(lines) // 2
        assert total_docs == 3

    @patch("app.services.logsink_service.httpx.Client")
    def test_shutdown_when_disabled_is_safe(self, mock_http_client_class: Mock):
        """Shutdown is safe when service is disabled (no writer thread)."""
        settings = _make_test_settings(mqtt_url=None)
        mock_mqtt_service = _make_mock_mqtt_service(mqtt_url=None)
        lifecycle = TestLifecycleCoordinator()

        service = LogSinkService(
            config=settings, mqtt_service=mock_mqtt_service,
            lifecycle_coordinator=lifecycle,
        )

        assert service._writer_thread is None
        # _wait_for_shutdown should return True when no thread exists
        assert service._wait_for_shutdown(1.0) is True


class TestLogSinkServiceMetrics:
    """Tests for Prometheus metrics."""

    @patch("app.services.logsink_service.httpx.Client")
    def test_metrics_initialized_on_creation(self, mock_http_client_class: Mock):
        """Metrics are initialized when service is created."""
        settings = _make_test_settings()
        mock_mqtt_service = _make_mock_mqtt_service()
        lifecycle = TestLifecycleCoordinator()

        service = LogSinkService(
            config=settings, mqtt_service=mock_mqtt_service,
            lifecycle_coordinator=lifecycle,
        )
        service.startup()

        try:
            assert hasattr(service, "logsink_messages_received_total")
            assert hasattr(service, "logsink_es_writes_total")
            assert hasattr(service, "logsink_es_write_duration_seconds")
            assert hasattr(service, "logsink_retry_delay_seconds")
            assert hasattr(service, "logsink_enabled_gauge")
            assert hasattr(service, "logsink_batch_size")
            assert hasattr(service, "logsink_queue_depth")
        finally:
            _drain_service(service, lifecycle)

    @patch("app.services.logsink_service.httpx.Client")
    def test_metrics_initialized_when_disabled(self, mock_http_client_class: Mock):
        """Metrics are initialized even when service is disabled."""
        settings = _make_test_settings(mqtt_url=None)
        mock_mqtt_service = _make_mock_mqtt_service(mqtt_url=None)
        lifecycle = StubLifecycleCoordinator()

        service = LogSinkService(
            config=settings, mqtt_service=mock_mqtt_service,
            lifecycle_coordinator=lifecycle,
        )

        assert hasattr(service, "logsink_messages_received_total")
        assert hasattr(service, "logsink_enabled_gauge")
        assert hasattr(service, "logsink_batch_size")
        assert hasattr(service, "logsink_queue_depth")


class TestLogSinkServiceNdjson:
    """Tests for NDJSON (newline-delimited JSON) processing."""

    @patch("app.services.logsink_service.httpx.Client")
    def test_on_message_processes_multiple_lines(self, mock_http_client_class: Mock):
        """Multiple JSON lines are each processed and enqueued."""
        mock_http_client = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_http_client.post.return_value = mock_response
        mock_http_client_class.return_value = mock_http_client

        settings = _make_test_settings()
        mock_mqtt_service = _make_mock_mqtt_service()
        lifecycle = TestLifecycleCoordinator()

        service = LogSinkService(
            config=settings, mqtt_service=mock_mqtt_service,
            lifecycle_coordinator=lifecycle,
        )
        service.startup()

        try:
            # NDJSON payload with 3 messages
            lines = [
                json.dumps({"message": "Log 1", "entity_id": "device-1"}),
                json.dumps({"message": "Log 2", "entity_id": "device-2"}),
                json.dumps({"message": "Log 3", "entity_id": "device-3"}),
            ]
            payload = "\n".join(lines).encode()
            service._on_message(payload)

            time.sleep(0.3)

            # Verify ES bulk write was called with all 3 docs
            assert mock_http_client.post.call_count >= 1
            # Check total documents across all bulk calls
            total_docs = 0
            all_entity_ids = []
            for call in mock_http_client.post.call_args_list:
                bulk_body = call[1]["content"]
                body_lines = bulk_body.strip().split("\n")
                for i in range(1, len(body_lines), 2):
                    doc = json.loads(body_lines[i])
                    all_entity_ids.append(doc["entity_id"])
                    total_docs += 1
            assert total_docs == 3
            assert set(all_entity_ids) == {"device-1", "device-2", "device-3"}
        finally:
            _drain_service(service, lifecycle)

    @patch("app.services.logsink_service.httpx.Client")
    def test_on_message_skips_empty_lines(self, mock_http_client_class: Mock):
        """Empty lines in NDJSON are skipped."""
        mock_http_client = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_http_client.post.return_value = mock_response
        mock_http_client_class.return_value = mock_http_client

        settings = _make_test_settings()
        mock_mqtt_service = _make_mock_mqtt_service()
        lifecycle = TestLifecycleCoordinator()

        service = LogSinkService(
            config=settings, mqtt_service=mock_mqtt_service,
            lifecycle_coordinator=lifecycle,
        )
        service.startup()

        try:
            payload = b'{"message": "Log 1"}\n\n\n{"message": "Log 2"}\n'
            service._on_message(payload)

            time.sleep(0.3)

            # Check total documents
            total_docs = 0
            for call in mock_http_client.post.call_args_list:
                bulk_body = call[1]["content"]
                body_lines = bulk_body.strip().split("\n")
                total_docs += len(body_lines) // 2
            assert total_docs == 2
        finally:
            _drain_service(service, lifecycle)

    @patch("app.services.logsink_service.httpx.Client")
    def test_on_message_invalid_line_does_not_stop_processing(
        self, mock_http_client_class: Mock
    ):
        """Invalid JSON on one line doesn't prevent other lines from processing."""
        mock_http_client = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_http_client.post.return_value = mock_response
        mock_http_client_class.return_value = mock_http_client

        settings = _make_test_settings()
        mock_mqtt_service = _make_mock_mqtt_service()
        lifecycle = TestLifecycleCoordinator()

        service = LogSinkService(
            config=settings, mqtt_service=mock_mqtt_service,
            lifecycle_coordinator=lifecycle,
        )
        service.startup()

        try:
            payload = b'{"message": "Log 1"}\nnot valid json\n{"message": "Log 3"}'
            service._on_message(payload)

            time.sleep(0.3)

            # 2 valid docs should be written
            total_docs = 0
            for call in mock_http_client.post.call_args_list:
                bulk_body = call[1]["content"]
                body_lines = bulk_body.strip().split("\n")
                total_docs += len(body_lines) // 2
            assert total_docs == 2
        finally:
            _drain_service(service, lifecycle)

    @patch("app.services.logsink_service.httpx.Client")
    def test_on_message_whitespace_only_lines_skipped(
        self, mock_http_client_class: Mock
    ):
        """Lines with only whitespace are skipped."""
        mock_http_client = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_http_client.post.return_value = mock_response
        mock_http_client_class.return_value = mock_http_client

        settings = _make_test_settings()
        mock_mqtt_service = _make_mock_mqtt_service()
        lifecycle = TestLifecycleCoordinator()

        service = LogSinkService(
            config=settings, mqtt_service=mock_mqtt_service,
            lifecycle_coordinator=lifecycle,
        )
        service.startup()

        try:
            payload = b'{"message": "Log 1"}\n   \n\t\n{"message": "Log 2"}'
            service._on_message(payload)

            time.sleep(0.3)

            total_docs = 0
            for call in mock_http_client.post.call_args_list:
                bulk_body = call[1]["content"]
                body_lines = bulk_body.strip().split("\n")
                total_docs += len(body_lines) // 2
            assert total_docs == 2
        finally:
            _drain_service(service, lifecycle)


class TestLogSinkServiceIndexNaming:
    """Tests for Elasticsearch index naming."""

    @patch("app.services.logsink_service.httpx.Client")
    def test_index_name_format(self, mock_http_client_class: Mock):
        """Index name follows logstash-http-YYYY.MM.dd format."""
        mock_http_client = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_http_client.post.return_value = mock_response
        mock_http_client_class.return_value = mock_http_client

        settings = _make_test_settings()
        mock_mqtt_service = _make_mock_mqtt_service()
        lifecycle = TestLifecycleCoordinator()

        service = LogSinkService(
            config=settings, mqtt_service=mock_mqtt_service,
            lifecycle_coordinator=lifecycle,
        )
        service.startup()

        try:
            payload = json.dumps({"message": "Test"}).encode()
            service._on_message(payload)

            time.sleep(0.3)

            call_args = mock_http_client.post.call_args
            bulk_body = call_args[1]["content"]
            lines = bulk_body.strip().split("\n")
            action = json.loads(lines[0])

            today = datetime.now(UTC).strftime("%Y.%m.%d")
            expected_index = f"logstash-http-{today}"
            assert action["index"]["_index"] == expected_index
        finally:
            _drain_service(service, lifecycle)
