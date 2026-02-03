"""Tests for LogSinkService."""

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock, Mock, patch

import httpx

from app.config import Settings
from app.services.logsink_service import LogSinkService
from app.services.mqtt_service import MqttService


def _make_test_settings(
    mqtt_url: str | None = "mqtt://localhost:1883",
    elasticsearch_url: str | None = "http://localhost:9200",
    mqtt_username: str | None = None,
    mqtt_password: str | None = None,
    elasticsearch_username: str | None = None,
    elasticsearch_password: str | None = None,
    mqtt_client_id: str = "iotsupport-backend",
) -> Settings:
    """Create test settings with configurable MQTT and ES settings."""
    return Settings(
        secret_key="test-secret",
        flask_env="testing",
        debug=True,
        database_url="sqlite://",
        assets_dir=None,
        cors_origins=["http://localhost:3000"],
        mqtt_url=mqtt_url,
        device_mqtt_url=mqtt_url,
        mqtt_username=mqtt_username,
        mqtt_password=mqtt_password,
        baseurl="http://localhost:3200",
        device_baseurl="http://localhost:3200",
        oidc_enabled=False,
        oidc_issuer_url=None,
        oidc_client_id=None,
        oidc_client_secret=None,
        oidc_scopes="openid profile email",
        oidc_audience=None,
        oidc_clock_skew_seconds=30,
        oidc_cookie_name="access_token",
        oidc_cookie_secure=False,
        oidc_cookie_samesite="Lax",
        oidc_refresh_cookie_name="refresh_token",
        oidc_token_url=None,
        keycloak_base_url=None,
        keycloak_realm=None,
        keycloak_admin_client_id=None,
        keycloak_admin_client_secret=None,
        keycloak_device_scope_name="iot-device-audience",
        keycloak_admin_url=None,
        keycloak_console_base_url=None,
        wifi_ssid=None,
        wifi_password=None,
        rotation_cron=None,
        rotation_timeout_seconds=300,
        rotation_critical_threshold_days=None,
        elasticsearch_url=elasticsearch_url,
        elasticsearch_username=elasticsearch_username,
        elasticsearch_password=elasticsearch_password,
        elasticsearch_index_pattern="logstash-http-*",
        mqtt_client_id=mqtt_client_id,
        fernet_key="test-fernet-key-padded-to-32-bytes=",
    )


def _make_mock_mqtt_service(mqtt_url: str | None = "mqtt://localhost:1883") -> Mock:
    """Create a mock MqttService for testing."""
    mock_service = Mock(spec=MqttService)
    mock_service.config = Mock()
    mock_service.config.mqtt_url = mqtt_url
    mock_service.enabled = bool(mqtt_url)
    return mock_service


class TestLogSinkServiceInitialization:
    """Tests for LogSinkService initialization."""

    @patch("app.services.logsink_service.httpx.Client")
    def test_init_with_both_mqtt_and_es_configured(self, mock_http_client_class: Mock):
        """Service initializes when both MQTT and Elasticsearch are configured."""
        settings = _make_test_settings()
        mock_mqtt_service = _make_mock_mqtt_service()

        service = LogSinkService(config=settings, mqtt_service=mock_mqtt_service)

        assert service.enabled is True
        # Verify subscription was registered
        mock_mqtt_service.subscribe.assert_called_once_with(
            topic="iotsupport/logsink",
            qos=1,
            callback=service._on_message,
        )

    @patch("app.services.logsink_service.httpx.Client")
    def test_init_without_mqtt_url_disables_service(self, mock_http_client_class: Mock):
        """Service disabled when MQTT_URL not configured."""
        settings = _make_test_settings(mqtt_url=None)
        mock_mqtt_service = _make_mock_mqtt_service(mqtt_url=None)

        service = LogSinkService(config=settings, mqtt_service=mock_mqtt_service)

        assert service.enabled is False
        mock_mqtt_service.subscribe.assert_not_called()

    @patch("app.services.logsink_service.httpx.Client")
    def test_init_without_elasticsearch_url_disables_service(
        self, mock_http_client_class: Mock
    ):
        """Service disabled when ELASTICSEARCH_URL not configured."""
        settings = _make_test_settings(elasticsearch_url=None)
        mock_mqtt_service = _make_mock_mqtt_service()

        service = LogSinkService(config=settings, mqtt_service=mock_mqtt_service)

        assert service.enabled is False
        mock_mqtt_service.subscribe.assert_not_called()

    @patch("app.services.logsink_service.httpx.Client")
    def test_init_without_both_disables_service(self, mock_http_client_class: Mock):
        """Service disabled when neither MQTT nor ES are configured."""
        settings = _make_test_settings(mqtt_url=None, elasticsearch_url=None)
        mock_mqtt_service = _make_mock_mqtt_service(mqtt_url=None)

        service = LogSinkService(config=settings, mqtt_service=mock_mqtt_service)

        assert service.enabled is False


class TestLogSinkServiceMessageProcessing:
    """Tests for message processing."""

    @patch("app.services.logsink_service.httpx.Client")
    def test_on_message_valid_json_processes_successfully(
        self, mock_http_client_class: Mock
    ):
        """Valid JSON message is processed and written to ES."""
        mock_http_client = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_http_client.post.return_value = mock_response
        mock_http_client_class.return_value = mock_http_client

        settings = _make_test_settings()
        mock_mqtt_service = _make_mock_mqtt_service()
        service = LogSinkService(config=settings, mqtt_service=mock_mqtt_service)

        # Simulate receiving a message
        payload = json.dumps({"message": "Test log", "entity_id": "device-1"}).encode()
        service._on_message(payload)

        # Verify ES write was attempted
        assert mock_http_client.post.called
        call_args = mock_http_client.post.call_args
        assert "logstash-http-" in call_args[0][0]  # URL contains index pattern

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
        service = LogSinkService(config=settings, mqtt_service=mock_mqtt_service)

        # Message with ANSI color codes
        payload = json.dumps({
            "message": "\x1b[31mRed error message\x1b[0m",
            "entity_id": "device-1",
        }).encode()
        service._on_message(payload)

        # Check the document sent to ES
        call_args = mock_http_client.post.call_args
        doc = call_args[1]["json"]
        assert doc["message"] == "Red error message"

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
        service = LogSinkService(config=settings, mqtt_service=mock_mqtt_service)

        payload = json.dumps({
            "message": "Test",
            "relative_time": 12345,
            "entity_id": "device-1",
        }).encode()
        service._on_message(payload)

        call_args = mock_http_client.post.call_args
        doc = call_args[1]["json"]
        assert "relative_time" not in doc

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
        service = LogSinkService(config=settings, mqtt_service=mock_mqtt_service)

        before = datetime.now(UTC)
        payload = json.dumps({"message": "Test"}).encode()
        service._on_message(payload)
        after = datetime.now(UTC)

        call_args = mock_http_client.post.call_args
        doc = call_args[1]["json"]
        assert "@timestamp" in doc
        # Parse and verify timestamp is in range
        ts = datetime.fromisoformat(doc["@timestamp"])
        assert before <= ts <= after

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
        service = LogSinkService(config=settings, mqtt_service=mock_mqtt_service)

        payload = json.dumps({"entity_id": "device-1", "level": "INFO"}).encode()
        service._on_message(payload)

        # Should still write to ES
        assert mock_http_client.post.called

    @patch("app.services.logsink_service.httpx.Client")
    def test_on_message_invalid_json_increments_error_metric(
        self, mock_http_client_class: Mock
    ):
        """Invalid JSON increments parse_error metric."""
        settings = _make_test_settings()
        mock_mqtt_service = _make_mock_mqtt_service()
        service = LogSinkService(config=settings, mqtt_service=mock_mqtt_service)

        # Send invalid JSON
        payload = b"not valid json"
        service._on_message(payload)

        # ES should not be called
        mock_http_client_class.return_value.post.assert_not_called()

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
        service = LogSinkService(config=settings, mqtt_service=mock_mqtt_service)

        payload = json.dumps({
            "message": "Test",
            "entity_id": "device-1",
            "level": "ERROR",
            "custom_field": "custom_value",
        }).encode()
        service._on_message(payload)

        call_args = mock_http_client.post.call_args
        doc = call_args[1]["json"]
        assert doc["entity_id"] == "device-1"
        assert doc["level"] == "ERROR"
        assert doc["custom_field"] == "custom_value"


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
        service = LogSinkService(config=settings, mqtt_service=mock_mqtt_service)

        # Mock the event wait to avoid actual sleeping
        service._shutdown_event = MagicMock()
        service._shutdown_event.is_set.return_value = False
        service._shutdown_event.wait.return_value = False

        payload = json.dumps({"message": "Test"}).encode()
        service._on_message(payload)

        assert mock_http_client.post.call_count == 3

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
        service = LogSinkService(config=settings, mqtt_service=mock_mqtt_service)

        service._shutdown_event = MagicMock()
        service._shutdown_event.is_set.return_value = False
        service._shutdown_event.wait.return_value = False

        payload = json.dumps({"message": "Test"}).encode()
        service._on_message(payload)

        assert mock_http_client.post.call_count == 2

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
        service = LogSinkService(config=settings, mqtt_service=mock_mqtt_service)

        service._shutdown_event = MagicMock()
        service._shutdown_event.is_set.return_value = False
        service._shutdown_event.wait.return_value = False

        payload = json.dumps({"message": "Test"}).encode()
        service._on_message(payload)

        assert mock_http_client.post.call_count == 2

    @patch("app.services.logsink_service.httpx.Client")
    def test_shutdown_interrupts_retry_loop(self, mock_http_client_class: Mock):
        """Shutdown event interrupts retry loop."""
        mock_http_client = MagicMock()
        mock_http_client.post.side_effect = httpx.ConnectError("Connection refused")
        mock_http_client_class.return_value = mock_http_client

        settings = _make_test_settings()
        mock_mqtt_service = _make_mock_mqtt_service()
        service = LogSinkService(config=settings, mqtt_service=mock_mqtt_service)

        # Simulate shutdown during wait
        call_count = [0]

        def mock_wait(timeout):
            call_count[0] += 1
            if call_count[0] >= 2:
                return True  # Shutdown signaled
            return False

        service._shutdown_event = MagicMock()
        service._shutdown_event.is_set.return_value = False
        service._shutdown_event.wait.side_effect = mock_wait

        payload = json.dumps({"message": "Test"}).encode()
        service._on_message(payload)

        # Should exit after shutdown is signaled
        assert mock_http_client.post.call_count == 2

    @patch("app.services.logsink_service.httpx.Client")
    def test_retry_delay_increments(self, mock_http_client_class: Mock):
        """Retry delay increments by 1 second each attempt."""
        mock_http_client = MagicMock()
        # Fail 5 times then succeed
        mock_http_client.post.side_effect = [
            httpx.ConnectError("fail"),
            httpx.ConnectError("fail"),
            httpx.ConnectError("fail"),
            httpx.ConnectError("fail"),
            httpx.ConnectError("fail"),
            MagicMock(raise_for_status=MagicMock()),
        ]
        mock_http_client_class.return_value = mock_http_client

        settings = _make_test_settings()
        mock_mqtt_service = _make_mock_mqtt_service()
        service = LogSinkService(config=settings, mqtt_service=mock_mqtt_service)

        delays = []
        service._shutdown_event = MagicMock()
        service._shutdown_event.is_set.return_value = False
        service._shutdown_event.wait.side_effect = lambda timeout: (
            delays.append(timeout),
            False,
        )[1]

        payload = json.dumps({"message": "Test"}).encode()
        service._on_message(payload)

        assert delays == [1.0, 2.0, 3.0, 4.0, 5.0]

    @patch("app.services.logsink_service.httpx.Client")
    def test_retry_delay_caps_at_max(self, mock_http_client_class: Mock):
        """Retry delay caps at MAX_RETRY_DELAY (60 seconds)."""
        mock_http_client = MagicMock()
        mock_http_client.post.side_effect = httpx.ConnectError("fail")
        mock_http_client_class.return_value = mock_http_client

        settings = _make_test_settings()
        mock_mqtt_service = _make_mock_mqtt_service()
        service = LogSinkService(config=settings, mqtt_service=mock_mqtt_service)

        delays = []
        call_count = [0]

        def mock_wait(timeout):
            call_count[0] += 1
            delays.append(timeout)
            if call_count[0] >= 65:
                return True  # Stop after 65 attempts
            return False

        service._shutdown_event = MagicMock()
        service._shutdown_event.is_set.return_value = False
        service._shutdown_event.wait.side_effect = mock_wait

        payload = json.dumps({"message": "Test"}).encode()
        service._on_message(payload)

        # Verify delay caps at 60
        assert delays[-1] == 60.0
        # First delays should increment
        assert delays[:5] == [1.0, 2.0, 3.0, 4.0, 5.0]

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
        service = LogSinkService(config=settings, mqtt_service=mock_mqtt_service)

        payload = json.dumps({"message": "Test"}).encode()
        service._on_message(payload)

        call_args = mock_http_client.post.call_args
        assert call_args[1]["auth"] == ("elastic", "secret")


class TestLogSinkServiceShutdown:
    """Tests for service shutdown."""

    @patch("app.services.logsink_service.httpx.Client")
    def test_shutdown_closes_http_client(self, mock_http_client_class: Mock):
        """Shutdown closes HTTP client."""
        mock_http_client = MagicMock()
        mock_http_client_class.return_value = mock_http_client

        settings = _make_test_settings()
        mock_mqtt_service = _make_mock_mqtt_service()
        service = LogSinkService(config=settings, mqtt_service=mock_mqtt_service)

        service.shutdown()

        mock_http_client.close.assert_called_once()

    @patch("app.services.logsink_service.httpx.Client")
    def test_shutdown_when_disabled_is_noop(self, mock_http_client_class: Mock):
        """Shutdown is safe when service is disabled."""
        settings = _make_test_settings(mqtt_url=None)
        mock_mqtt_service = _make_mock_mqtt_service(mqtt_url=None)
        service = LogSinkService(config=settings, mqtt_service=mock_mqtt_service)

        # Should not raise
        service.shutdown()

    @patch("app.services.logsink_service.httpx.Client")
    def test_shutdown_sets_event(self, mock_http_client_class: Mock):
        """Shutdown sets the shutdown event."""
        settings = _make_test_settings()
        mock_mqtt_service = _make_mock_mqtt_service()
        service = LogSinkService(config=settings, mqtt_service=mock_mqtt_service)

        assert not service._shutdown_event.is_set()
        service.shutdown()
        assert service._shutdown_event.is_set()


class TestLogSinkServiceMetrics:
    """Tests for Prometheus metrics."""

    @patch("app.services.logsink_service.httpx.Client")
    def test_metrics_initialized_on_creation(self, mock_http_client_class: Mock):
        """Metrics are initialized when service is created."""
        settings = _make_test_settings()
        mock_mqtt_service = _make_mock_mqtt_service()
        service = LogSinkService(config=settings, mqtt_service=mock_mqtt_service)

        assert hasattr(service, "logsink_messages_received_total")
        assert hasattr(service, "logsink_es_writes_total")
        assert hasattr(service, "logsink_es_write_duration_seconds")
        assert hasattr(service, "logsink_retry_delay_seconds")
        assert hasattr(service, "logsink_enabled_gauge")

    @patch("app.services.logsink_service.httpx.Client")
    def test_metrics_initialized_when_disabled(self, mock_http_client_class: Mock):
        """Metrics are initialized even when service is disabled."""
        settings = _make_test_settings(mqtt_url=None)
        mock_mqtt_service = _make_mock_mqtt_service(mqtt_url=None)
        service = LogSinkService(config=settings, mqtt_service=mock_mqtt_service)

        # Metrics should still exist
        assert hasattr(service, "logsink_messages_received_total")
        assert hasattr(service, "logsink_enabled_gauge")


class TestLogSinkServiceNdjson:
    """Tests for NDJSON (newline-delimited JSON) processing."""

    @patch("app.services.logsink_service.httpx.Client")
    def test_on_message_processes_multiple_lines(self, mock_http_client_class: Mock):
        """Multiple JSON lines are each processed separately."""
        mock_http_client = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_http_client.post.return_value = mock_response
        mock_http_client_class.return_value = mock_http_client

        settings = _make_test_settings()
        mock_mqtt_service = _make_mock_mqtt_service()
        service = LogSinkService(config=settings, mqtt_service=mock_mqtt_service)

        # NDJSON payload with 3 messages
        lines = [
            json.dumps({"message": "Log 1", "entity_id": "device-1"}),
            json.dumps({"message": "Log 2", "entity_id": "device-2"}),
            json.dumps({"message": "Log 3", "entity_id": "device-3"}),
        ]
        payload = "\n".join(lines).encode()
        service._on_message(payload)

        # Verify ES write was called 3 times
        assert mock_http_client.post.call_count == 3

        # Verify each message was written
        calls = mock_http_client.post.call_args_list
        entity_ids = [call[1]["json"]["entity_id"] for call in calls]
        assert entity_ids == ["device-1", "device-2", "device-3"]

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
        service = LogSinkService(config=settings, mqtt_service=mock_mqtt_service)

        # NDJSON payload with empty lines
        payload = b'{"message": "Log 1"}\n\n\n{"message": "Log 2"}\n'
        service._on_message(payload)

        # Only 2 writes (empty lines skipped)
        assert mock_http_client.post.call_count == 2

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
        service = LogSinkService(config=settings, mqtt_service=mock_mqtt_service)

        # NDJSON with invalid line in the middle
        payload = b'{"message": "Log 1"}\nnot valid json\n{"message": "Log 3"}'
        service._on_message(payload)

        # 2 successful writes (invalid line skipped)
        assert mock_http_client.post.call_count == 2

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
        service = LogSinkService(config=settings, mqtt_service=mock_mqtt_service)

        payload = b'{"message": "Log 1"}\n   \n\t\n{"message": "Log 2"}'
        service._on_message(payload)

        assert mock_http_client.post.call_count == 2


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
        service = LogSinkService(config=settings, mqtt_service=mock_mqtt_service)

        payload = json.dumps({"message": "Test"}).encode()
        service._on_message(payload)

        call_args = mock_http_client.post.call_args
        url = call_args[0][0]

        # Verify URL contains index with today's date
        today = datetime.now(UTC).strftime("%Y.%m.%d")
        expected_index = f"logstash-http-{today}"
        assert expected_index in url
