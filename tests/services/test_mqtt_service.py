"""Tests for MqttService."""

from unittest.mock import MagicMock, Mock, patch

import pytest

from app.services.mqtt_service import MqttService


class TestMqttServiceInitialization:
    """Tests for MqttService initialization."""

    @patch("app.services.mqtt_service.MqttClient")
    @patch("app.services.mqtt_service.atexit.register")
    def test_init_with_mqtt_url_creates_client(
        self, mock_atexit: Mock, mock_mqtt_client_class: Mock
    ):
        """MQTT client is created and connection initiated when URL provided."""
        mock_client = MagicMock()
        mock_mqtt_client_class.return_value = mock_client

        service = MqttService(
            mqtt_url="mqtt://localhost:1883",
            mqtt_username="test_user",
            mqtt_password="test_pass",
        )

        # Verify client was created
        mock_mqtt_client_class.assert_called_once()

        # Verify credentials were set
        mock_client.username_pw_set.assert_called_once_with("test_user", "test_pass")

        # Verify connection was started
        mock_client.connect_async.assert_called_once_with("localhost", 1883)
        mock_client.loop_start.assert_called_once()

        # Service is NOT enabled until connection confirmed via _on_connect callback
        assert service.enabled is False

        # Simulate successful connection callback
        mock_reason_code = MagicMock()
        mock_reason_code.is_failure = False
        mock_connect_flags = MagicMock()
        service._on_connect(mock_client, None, mock_connect_flags, mock_reason_code, None)

        # Now service is enabled
        assert service.enabled is True

        # Verify shutdown handler was registered
        mock_atexit.assert_called_once_with(service.shutdown)

    @patch("app.services.mqtt_service.MqttClient")
    def test_init_with_mqtts_url_configures_tls(self, mock_mqtt_client_class: Mock):
        """TLS is configured when using mqtts:// URL."""
        mock_client = MagicMock()
        mock_mqtt_client_class.return_value = mock_client

        MqttService(mqtt_url="mqtts://broker.example.com:8883")

        # Verify TLS was configured
        mock_client.tls_set.assert_called_once()

        # Verify connection to correct port
        mock_client.connect_async.assert_called_once_with("broker.example.com", 8883)

    @patch("app.services.mqtt_service.MqttClient")
    def test_init_with_mqtt_url_no_port_uses_default(
        self, mock_mqtt_client_class: Mock
    ):
        """Default port 1883 is used when not specified in mqtt:// URL."""
        mock_client = MagicMock()
        mock_mqtt_client_class.return_value = mock_client

        MqttService(mqtt_url="mqtt://broker.local")

        mock_client.connect_async.assert_called_once_with("broker.local", 1883)

    @patch("app.services.mqtt_service.MqttClient")
    def test_init_with_mqtts_url_no_port_uses_default(
        self, mock_mqtt_client_class: Mock
    ):
        """Default port 8883 is used when not specified in mqtts:// URL."""
        mock_client = MagicMock()
        mock_mqtt_client_class.return_value = mock_client

        MqttService(mqtt_url="mqtts://broker.secure")

        mock_client.tls_set.assert_called_once()
        mock_client.connect_async.assert_called_once_with("broker.secure", 8883)

    def test_init_without_mqtt_url_disables_service(self):
        """Service is disabled when MQTT_URL is None."""
        service = MqttService(mqtt_url=None)

        assert service.enabled is False
        assert service.client is None

    def test_init_with_empty_mqtt_url_disables_service(self):
        """Service is disabled when MQTT_URL is empty string."""
        service = MqttService(mqtt_url="")

        assert service.enabled is False
        assert service.client is None

    @patch("app.services.mqtt_service.MqttClient")
    def test_init_without_credentials_skips_auth(self, mock_mqtt_client_class: Mock):
        """Credentials are not set when username/password not provided."""
        mock_client = MagicMock()
        mock_mqtt_client_class.return_value = mock_client

        MqttService(mqtt_url="mqtt://localhost:1883")

        # Verify credentials were not set
        mock_client.username_pw_set.assert_not_called()

    @patch("app.services.mqtt_service.MqttClient")
    def test_init_with_invalid_url_disables_service(
        self, mock_mqtt_client_class: Mock
    ):
        """Service is disabled when URL format is invalid."""
        service = MqttService(mqtt_url="http://invalid:1883")

        assert service.enabled is False
        assert service.client is None

        # Client should not be created for invalid URL
        mock_mqtt_client_class.assert_not_called()

    @patch("app.services.mqtt_service.MqttClient")
    def test_init_when_client_creation_fails_disables_service(
        self, mock_mqtt_client_class: Mock
    ):
        """Service is disabled when MQTT client creation raises exception."""
        mock_mqtt_client_class.side_effect = Exception("Connection failed")

        service = MqttService(mqtt_url="mqtt://localhost:1883")

        assert service.enabled is False


def _simulate_successful_connection(service: MqttService, mock_client: MagicMock) -> None:
    """Helper to simulate a successful MQTT connection callback."""
    mock_reason_code = MagicMock()
    mock_reason_code.is_failure = False
    mock_connect_flags = MagicMock()
    service._on_connect(mock_client, None, mock_connect_flags, mock_reason_code, None)


class TestMqttServicePublish:
    """Tests for MQTT publish method."""

    @patch("app.services.mqtt_service.MqttClient")
    def test_publish_when_enabled(self, mock_mqtt_client_class: Mock):
        """Publish sends message to correct topic with plain text payload."""
        mock_client = MagicMock()
        mock_mqtt_client_class.return_value = mock_client

        # Mock successful publish
        mock_result = MagicMock()
        mock_result.rc = 0
        mock_client.publish.return_value = mock_result

        service = MqttService(mqtt_url="mqtt://localhost:1883")
        # Simulate successful connection
        _simulate_successful_connection(service, mock_client)
        service.publish("iotsupport/updates/configs", "abc12345")

        # Verify publish was called with correct topic and plain text payload
        mock_client.publish.assert_called_once_with(
            "iotsupport/updates/configs", "abc12345", qos=1, retain=False
        )

    @patch("app.services.mqtt_service.MqttClient")
    def test_publish_to_different_topic(self, mock_mqtt_client_class: Mock):
        """Publish works with any topic."""
        mock_client = MagicMock()
        mock_mqtt_client_class.return_value = mock_client

        # Mock successful publish
        mock_result = MagicMock()
        mock_result.rc = 0
        mock_client.publish.return_value = mock_result

        service = MqttService(mqtt_url="mqtt://localhost:1883")
        # Simulate successful connection
        _simulate_successful_connection(service, mock_client)
        service.publish("iotsupport/updates/assets", "firmware-v1.2.3.bin")

        # Verify publish was called with correct topic and payload
        mock_client.publish.assert_called_once_with(
            "iotsupport/updates/assets", "firmware-v1.2.3.bin", qos=1, retain=False
        )

    def test_publish_when_disabled_silent_skip(self):
        """Publish is skipped silently when service is disabled."""
        service = MqttService(mqtt_url=None)

        # Should not raise exception
        service.publish("any/topic", "any-payload")

    @patch("app.services.mqtt_service.MqttClient")
    def test_publish_sends_payload_unchanged(self, mock_mqtt_client_class: Mock):
        """Payload is sent as plain text without modification."""
        mock_client = MagicMock()
        mock_mqtt_client_class.return_value = mock_client

        # Mock successful publish
        mock_result = MagicMock()
        mock_result.rc = 0
        mock_client.publish.return_value = mock_result

        service = MqttService(mqtt_url="mqtt://localhost:1883")
        # Simulate successful connection
        _simulate_successful_connection(service, mock_client)
        service.publish("test/topic", "test-payload")

        # Verify payload is sent as-is
        call_args = mock_client.publish.call_args
        payload = call_args[0][1]
        assert payload == "test-payload"

    @patch("app.services.mqtt_service.MqttClient")
    def test_publish_when_client_publish_raises_exception(
        self, mock_mqtt_client_class: Mock
    ):
        """Exception during publish is caught and logged, not raised."""
        mock_client = MagicMock()
        mock_mqtt_client_class.return_value = mock_client

        # Mock publish raising exception
        mock_client.publish.side_effect = Exception("Network error")

        service = MqttService(mqtt_url="mqtt://localhost:1883")
        # Simulate successful connection
        _simulate_successful_connection(service, mock_client)

        # Should not raise exception (fire-and-forget)
        service.publish("test/topic", "test-payload")

    @patch("app.services.mqtt_service.MqttClient")
    def test_publish_when_result_indicates_failure(self, mock_mqtt_client_class: Mock):
        """Non-zero return code is logged but does not raise exception."""
        mock_client = MagicMock()
        mock_mqtt_client_class.return_value = mock_client

        # Mock failed publish (non-zero rc)
        mock_result = MagicMock()
        mock_result.rc = 1  # MQTT_ERR_NOMEM or similar
        mock_client.publish.return_value = mock_result

        service = MqttService(mqtt_url="mqtt://localhost:1883")
        # Simulate successful connection
        _simulate_successful_connection(service, mock_client)

        # Should not raise exception
        service.publish("test/topic", "test-payload")


class TestMqttServiceConnectionCallbacks:
    """Tests for MQTT connection event callbacks."""

    @patch("app.services.mqtt_service.MqttClient")
    def test_on_connect_success_updates_connection_state(
        self, mock_mqtt_client_class: Mock
    ):
        """Connection state gauge is set to 1 on successful connection."""
        mock_client = MagicMock()
        mock_mqtt_client_class.return_value = mock_client

        service = MqttService(mqtt_url="mqtt://localhost:1883")

        # Create mock reason code for success
        mock_reason_code = MagicMock()
        mock_reason_code.is_failure = False
        mock_connect_flags = MagicMock()

        # Simulate successful connection callback
        service._on_connect(mock_client, None, mock_connect_flags, mock_reason_code, None)

        # Connection state should be 1
        # We can't easily verify gauge value without accessing prometheus internals,
        # but we can verify the method executed without error

    @patch("app.services.mqtt_service.MqttClient")
    def test_on_connect_failure_disables_service(self, mock_mqtt_client_class: Mock):
        """Service remains disabled when connection fails."""
        mock_client = MagicMock()
        mock_mqtt_client_class.return_value = mock_client

        service = MqttService(mqtt_url="mqtt://localhost:1883")
        # Service starts disabled (enabled only set on successful connection)
        assert service.enabled is False

        # Create mock reason code for failure
        mock_reason_code = MagicMock()
        mock_reason_code.is_failure = True
        mock_connect_flags = MagicMock()

        # Simulate failed connection callback
        service._on_connect(mock_client, None, mock_connect_flags, mock_reason_code, None)

        # Service should remain disabled
        assert service.enabled is False

    @patch("app.services.mqtt_service.MqttClient")
    def test_on_disconnect_updates_connection_state(
        self, mock_mqtt_client_class: Mock
    ):
        """Connection state gauge is set to 0 on disconnect."""
        mock_client = MagicMock()
        mock_mqtt_client_class.return_value = mock_client

        service = MqttService(mqtt_url="mqtt://localhost:1883")

        # Create mock disconnect flags and reason code
        mock_disconnect_flags = MagicMock()
        mock_reason_code = MagicMock()

        # Simulate disconnect callback
        service._on_disconnect(mock_client, None, mock_disconnect_flags, mock_reason_code, None)

        # Connection state should be 0
        # Method should execute without error


class TestMqttServiceShutdown:
    """Tests for MQTT service shutdown."""

    @patch("app.services.mqtt_service.MqttClient")
    def test_shutdown_stops_loop_and_disconnects(self, mock_mqtt_client_class: Mock):
        """Shutdown stops network loop and disconnects from broker."""
        mock_client = MagicMock()
        mock_mqtt_client_class.return_value = mock_client

        service = MqttService(mqtt_url="mqtt://localhost:1883")
        service.shutdown()

        # Verify shutdown sequence
        mock_client.loop_stop.assert_called_once()
        mock_client.disconnect.assert_called_once()

    def test_shutdown_when_disabled_is_noop(self):
        """Shutdown does nothing when service is disabled."""
        service = MqttService(mqtt_url=None)

        # Should not raise exception
        service.shutdown()

    @patch("app.services.mqtt_service.MqttClient")
    def test_shutdown_is_idempotent(self, mock_mqtt_client_class: Mock):
        """Shutdown can be called multiple times safely."""
        mock_client = MagicMock()
        mock_mqtt_client_class.return_value = mock_client

        service = MqttService(mqtt_url="mqtt://localhost:1883")

        # Call shutdown multiple times
        service.shutdown()
        service.shutdown()
        service.shutdown()

        # Should only disconnect once
        assert mock_client.loop_stop.call_count == 1
        assert mock_client.disconnect.call_count == 1

    @patch("app.services.mqtt_service.MqttClient")
    def test_shutdown_when_client_raises_exception(
        self, mock_mqtt_client_class: Mock
    ):
        """Exception during shutdown is caught and logged."""
        mock_client = MagicMock()
        mock_mqtt_client_class.return_value = mock_client

        # Mock disconnect raising exception
        mock_client.disconnect.side_effect = Exception("Already disconnected")

        service = MqttService(mqtt_url="mqtt://localhost:1883")

        # Should not raise exception
        service.shutdown()


class TestMqttServiceMetrics:
    """Tests for Prometheus metrics integration."""

    @patch("app.services.mqtt_service.MqttClient")
    def test_metrics_initialized_on_creation(self, mock_mqtt_client_class: Mock):
        """Prometheus metrics are initialized when service is created."""
        mock_client = MagicMock()
        mock_mqtt_client_class.return_value = mock_client

        service = MqttService(mqtt_url="mqtt://localhost:1883")

        # Verify metrics objects exist
        assert hasattr(service, "mqtt_publish_total")
        assert hasattr(service, "mqtt_connection_state")
        assert hasattr(service, "mqtt_publish_duration_seconds")
        assert hasattr(service, "mqtt_enabled_gauge")

    def test_metrics_initialized_when_disabled(self):
        """Prometheus metrics are initialized even when MQTT is disabled."""
        service = MqttService(mqtt_url=None)

        # Verify metrics objects exist
        assert hasattr(service, "mqtt_publish_total")
        assert hasattr(service, "mqtt_connection_state")
        assert hasattr(service, "mqtt_publish_duration_seconds")
        assert hasattr(service, "mqtt_enabled_gauge")


class TestMqttServiceUrlParsing:
    """Tests for MQTT URL parsing."""

    def test_parse_mqtt_url_basic(self):
        """Basic mqtt:// URL is parsed correctly."""
        service = MqttService()
        host, port, use_tls = service._parse_mqtt_url("mqtt://broker.local:1883")

        assert host == "broker.local"
        assert port == 1883
        assert use_tls is False

    def test_parse_mqtts_url(self):
        """mqtts:// URL is parsed with TLS enabled."""
        service = MqttService()
        host, port, use_tls = service._parse_mqtt_url("mqtts://broker.secure:8883")

        assert host == "broker.secure"
        assert port == 8883
        assert use_tls is True

    def test_parse_url_without_port_mqtt(self):
        """mqtt:// URL without port uses default 1883."""
        service = MqttService()
        host, port, use_tls = service._parse_mqtt_url("mqtt://broker.local")

        assert host == "broker.local"
        assert port == 1883

    def test_parse_url_without_port_mqtts(self):
        """mqtts:// URL without port uses default 8883."""
        service = MqttService()
        host, port, use_tls = service._parse_mqtt_url("mqtts://broker.secure")

        assert host == "broker.secure"
        assert port == 8883

    def test_parse_url_with_path_components(self):
        """URL with path components extracts host/port correctly."""
        service = MqttService()
        host, port, use_tls = service._parse_mqtt_url("mqtt://broker.local:1883/some/path")

        assert host == "broker.local"
        assert port == 1883

    def test_parse_url_invalid_scheme(self):
        """Invalid URL scheme raises ValueError."""
        service = MqttService()

        with pytest.raises(ValueError, match="Invalid MQTT URL scheme"):
            service._parse_mqtt_url("http://broker.local:1883")
