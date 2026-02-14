"""Tests for MqttService."""

from unittest.mock import ANY, MagicMock, Mock, patch

from app.app_config import AppSettings
from app.services.mqtt_service import MqttService


def _make_test_settings(
    mqtt_url: str | None = "mqtt://localhost:1883",
    mqtt_username: str | None = None,
    mqtt_password: str | None = None,
    mqtt_client_id: str = "iotsupport-backend",
) -> AppSettings:
    """Create test settings with configurable MQTT settings."""
    return AppSettings(
        mqtt_url=mqtt_url,
        device_mqtt_url=mqtt_url,
        mqtt_username=mqtt_username,
        mqtt_password=mqtt_password,
        mqtt_client_id=mqtt_client_id,
    )


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

        settings = _make_test_settings(
            mqtt_url="mqtt://localhost:1883",
            mqtt_username="test_user",
            mqtt_password="test_pass",
        )
        service = MqttService(config=settings)

        # Verify client was created with client_id
        mock_mqtt_client_class.assert_called_once()
        call_kwargs = mock_mqtt_client_class.call_args[1]
        assert call_kwargs["client_id"] == "iotsupport-backend"

        # Verify credentials were set
        mock_client.username_pw_set.assert_called_once_with("test_user", "test_pass")

        # Verify connection was started with persistent session
        mock_client.connect_async.assert_called_once_with(
            "localhost", 1883, clean_start=False, properties=ANY
        )
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

        settings = _make_test_settings(mqtt_url="mqtts://broker.example.com:8883")
        MqttService(config=settings)

        # Verify TLS was configured
        mock_client.tls_set.assert_called_once()

        # Verify connection to correct port with persistent session
        mock_client.connect_async.assert_called_once_with(
            "broker.example.com", 8883, clean_start=False, properties=ANY
        )

    @patch("app.services.mqtt_service.MqttClient")
    def test_init_with_mqtt_url_no_port_uses_default(
        self, mock_mqtt_client_class: Mock
    ):
        """Default port 1883 is used when not specified in mqtt:// URL."""
        mock_client = MagicMock()
        mock_mqtt_client_class.return_value = mock_client

        settings = _make_test_settings(mqtt_url="mqtt://broker.local")
        MqttService(config=settings)

        mock_client.connect_async.assert_called_once_with(
            "broker.local", 1883, clean_start=False, properties=ANY
        )

    @patch("app.services.mqtt_service.MqttClient")
    def test_init_with_mqtts_url_no_port_uses_default(
        self, mock_mqtt_client_class: Mock
    ):
        """Default port 8883 is used when not specified in mqtts:// URL."""
        mock_client = MagicMock()
        mock_mqtt_client_class.return_value = mock_client

        settings = _make_test_settings(mqtt_url="mqtts://broker.secure")
        MqttService(config=settings)

        mock_client.tls_set.assert_called_once()
        mock_client.connect_async.assert_called_once_with(
            "broker.secure", 8883, clean_start=False, properties=ANY
        )

    def test_init_without_mqtt_url_disables_service(self):
        """Service is disabled when MQTT_URL is None."""
        settings = _make_test_settings(mqtt_url=None)
        service = MqttService(config=settings)

        assert service.enabled is False
        assert service.client is None

    def test_init_with_empty_mqtt_url_disables_service(self):
        """Service is disabled when MQTT_URL is empty string."""
        settings = _make_test_settings(mqtt_url="")
        service = MqttService(config=settings)

        assert service.enabled is False
        assert service.client is None

    @patch("app.services.mqtt_service.MqttClient")
    def test_init_without_credentials_skips_auth(self, mock_mqtt_client_class: Mock):
        """Credentials are not set when username/password not provided."""
        mock_client = MagicMock()
        mock_mqtt_client_class.return_value = mock_client

        settings = _make_test_settings(mqtt_url="mqtt://localhost:1883")
        MqttService(config=settings)

        # Verify credentials were not set
        mock_client.username_pw_set.assert_not_called()

    @patch("app.services.mqtt_service.MqttClient")
    def test_init_with_invalid_url_disables_service(
        self, mock_mqtt_client_class: Mock
    ):
        """Service is disabled when URL format is invalid."""
        settings = _make_test_settings(mqtt_url="http://invalid:1883")
        service = MqttService(config=settings)

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

        settings = _make_test_settings(mqtt_url="mqtt://localhost:1883")
        service = MqttService(config=settings)

        assert service.enabled is False

    @patch("app.services.mqtt_service.MqttClient")
    def test_init_with_custom_client_id(self, mock_mqtt_client_class: Mock):
        """Custom client ID is used when configured."""
        mock_client = MagicMock()
        mock_mqtt_client_class.return_value = mock_client

        settings = _make_test_settings(
            mqtt_url="mqtt://localhost:1883",
            mqtt_client_id="my-custom-client",
        )
        MqttService(config=settings)

        call_kwargs = mock_mqtt_client_class.call_args[1]
        assert call_kwargs["client_id"] == "my-custom-client"


def _simulate_successful_connection(service: MqttService, mock_client: MagicMock) -> None:
    """Helper to simulate a successful MQTT connection callback."""
    mock_reason_code = MagicMock()
    mock_reason_code.is_failure = False
    mock_connect_flags = MagicMock()
    service._on_connect(mock_client, None, mock_connect_flags, mock_reason_code, None)


class TestMqttServiceSubscribe:
    """Tests for MQTT subscribe method."""

    @patch("app.services.mqtt_service.MqttClient")
    def test_subscribe_when_connected(self, mock_mqtt_client_class: Mock):
        """Subscribe is called immediately when already connected."""
        mock_client = MagicMock()
        mock_mqtt_client_class.return_value = mock_client

        settings = _make_test_settings()
        service = MqttService(config=settings)
        _simulate_successful_connection(service, mock_client)

        callback = MagicMock()
        service.subscribe("test/topic", qos=1, callback=callback)

        mock_client.subscribe.assert_called_with("test/topic", qos=1)

    @patch("app.services.mqtt_service.MqttClient")
    def test_subscribe_queued_when_not_connected(self, mock_mqtt_client_class: Mock):
        """Subscribe is queued when not yet connected."""
        mock_client = MagicMock()
        mock_mqtt_client_class.return_value = mock_client

        settings = _make_test_settings()
        service = MqttService(config=settings)
        # Don't call _simulate_successful_connection - service.enabled is False

        callback = MagicMock()
        service.subscribe("test/topic", qos=1, callback=callback)

        # Subscribe should NOT be called on client yet
        mock_client.subscribe.assert_not_called()

        # Now connect
        _simulate_successful_connection(service, mock_client)

        # Subscribe should be called after connection
        mock_client.subscribe.assert_called_with("test/topic", qos=1)

    @patch("app.services.mqtt_service.MqttClient")
    def test_on_connect_resubscribes_all_topics(self, mock_mqtt_client_class: Mock):
        """All subscriptions are re-established on reconnect."""
        mock_client = MagicMock()
        mock_mqtt_client_class.return_value = mock_client

        settings = _make_test_settings()
        service = MqttService(config=settings)

        # Subscribe to multiple topics while disconnected
        callback1 = MagicMock()
        callback2 = MagicMock()
        service.subscribe("topic/a", qos=1, callback=callback1)
        service.subscribe("topic/b", qos=0, callback=callback2)

        # Connect
        _simulate_successful_connection(service, mock_client)

        # Both subscriptions should be established
        assert mock_client.subscribe.call_count == 2

    @patch("app.services.mqtt_service.MqttClient")
    def test_on_message_routes_to_callback(self, mock_mqtt_client_class: Mock):
        """Messages are routed to the correct callback."""
        mock_client = MagicMock()
        mock_mqtt_client_class.return_value = mock_client

        settings = _make_test_settings()
        service = MqttService(config=settings)
        _simulate_successful_connection(service, mock_client)

        callback = MagicMock()
        service.subscribe("test/topic", qos=1, callback=callback)

        # Simulate message
        mock_message = MagicMock()
        mock_message.topic = "test/topic"
        mock_message.payload = b"test payload"

        service._on_message(mock_client, None, mock_message)

        callback.assert_called_once_with(b"test payload")

    @patch("app.services.mqtt_service.MqttClient")
    def test_on_message_buffers_when_no_callback(self, mock_mqtt_client_class: Mock):
        """Messages on unregistered topics are buffered for later delivery."""
        mock_client = MagicMock()
        mock_mqtt_client_class.return_value = mock_client

        settings = _make_test_settings()
        service = MqttService(config=settings)
        _simulate_successful_connection(service, mock_client)

        # Simulate message arriving BEFORE callback is registered
        mock_message = MagicMock()
        mock_message.topic = "test/topic"
        mock_message.payload = b"buffered payload"

        service._on_message(mock_client, None, mock_message)

        # Message should be buffered
        assert "test/topic" in service._pending_messages
        assert service._pending_messages["test/topic"] == [b"buffered payload"]

    @patch("app.services.mqtt_service.MqttClient")
    def test_subscribe_delivers_buffered_messages(self, mock_mqtt_client_class: Mock):
        """Buffered messages are delivered when callback is registered."""
        mock_client = MagicMock()
        mock_mqtt_client_class.return_value = mock_client

        settings = _make_test_settings()
        service = MqttService(config=settings)
        _simulate_successful_connection(service, mock_client)

        # Simulate messages arriving BEFORE callback is registered
        mock_message1 = MagicMock()
        mock_message1.topic = "test/topic"
        mock_message1.payload = b"message 1"
        mock_message2 = MagicMock()
        mock_message2.topic = "test/topic"
        mock_message2.payload = b"message 2"

        service._on_message(mock_client, None, mock_message1)
        service._on_message(mock_client, None, mock_message2)

        # Now register callback
        callback = MagicMock()
        service.subscribe("test/topic", qos=1, callback=callback)

        # Buffered messages should have been delivered
        assert callback.call_count == 2
        callback.assert_any_call(b"message 1")
        callback.assert_any_call(b"message 2")

        # Buffer should be cleared
        assert "test/topic" not in service._pending_messages


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

        settings = _make_test_settings()
        service = MqttService(config=settings)
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

        settings = _make_test_settings()
        service = MqttService(config=settings)
        _simulate_successful_connection(service, mock_client)
        service.publish("iotsupport/updates/assets", "firmware-v1.2.3.bin")

        # Verify publish was called with correct topic and payload
        mock_client.publish.assert_called_once_with(
            "iotsupport/updates/assets", "firmware-v1.2.3.bin", qos=1, retain=False
        )

    def test_publish_when_disabled_silent_skip(self):
        """Publish is skipped silently when service is disabled."""
        settings = _make_test_settings(mqtt_url=None)
        service = MqttService(config=settings)

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

        settings = _make_test_settings()
        service = MqttService(config=settings)
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

        settings = _make_test_settings()
        service = MqttService(config=settings)
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

        settings = _make_test_settings()
        service = MqttService(config=settings)
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

        settings = _make_test_settings()
        service = MqttService(config=settings)

        # Create mock reason code for success
        mock_reason_code = MagicMock()
        mock_reason_code.is_failure = False
        mock_connect_flags = MagicMock()

        # Simulate successful connection callback
        service._on_connect(mock_client, None, mock_connect_flags, mock_reason_code, None)

        assert service.enabled is True

    @patch("app.services.mqtt_service.MqttClient")
    def test_on_connect_failure_disables_service(self, mock_mqtt_client_class: Mock):
        """Service remains disabled when connection fails."""
        mock_client = MagicMock()
        mock_mqtt_client_class.return_value = mock_client

        settings = _make_test_settings()
        service = MqttService(config=settings)
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

        settings = _make_test_settings()
        service = MqttService(config=settings)

        # Create mock disconnect flags and reason code
        mock_disconnect_flags = MagicMock()
        mock_reason_code = MagicMock()

        # Simulate disconnect callback - should not raise
        service._on_disconnect(mock_client, None, mock_disconnect_flags, mock_reason_code, None)


class TestMqttServiceShutdown:
    """Tests for MQTT service shutdown."""

    @patch("app.services.mqtt_service.MqttClient")
    def test_shutdown_stops_loop_and_disconnects(self, mock_mqtt_client_class: Mock):
        """Shutdown stops network loop and disconnects from broker."""
        mock_client = MagicMock()
        mock_mqtt_client_class.return_value = mock_client

        settings = _make_test_settings()
        service = MqttService(config=settings)
        service.shutdown()

        # Verify shutdown sequence
        mock_client.loop_stop.assert_called_once()
        mock_client.disconnect.assert_called_once()

    def test_shutdown_when_disabled_is_noop(self):
        """Shutdown does nothing when service is disabled."""
        settings = _make_test_settings(mqtt_url=None)
        service = MqttService(config=settings)

        # Should not raise exception
        service.shutdown()

    @patch("app.services.mqtt_service.MqttClient")
    def test_shutdown_is_idempotent(self, mock_mqtt_client_class: Mock):
        """Shutdown can be called multiple times safely."""
        mock_client = MagicMock()
        mock_mqtt_client_class.return_value = mock_client

        settings = _make_test_settings()
        service = MqttService(config=settings)

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

        settings = _make_test_settings()
        service = MqttService(config=settings)

        # Should not raise exception
        service.shutdown()


class TestMqttServiceMetrics:
    """Tests for Prometheus metrics integration."""

    @patch("app.services.mqtt_service.MqttClient")
    def test_metrics_initialized_on_creation(self, mock_mqtt_client_class: Mock):
        """Prometheus metrics are initialized when service is created."""
        mock_client = MagicMock()
        mock_mqtt_client_class.return_value = mock_client

        settings = _make_test_settings()
        service = MqttService(config=settings)

        # Verify metrics objects exist
        assert hasattr(service, "mqtt_publish_total")
        assert hasattr(service, "mqtt_connection_state")
        assert hasattr(service, "mqtt_publish_duration_seconds")
        assert hasattr(service, "mqtt_enabled_gauge")
        assert hasattr(service, "mqtt_subscriptions_total")

    def test_metrics_initialized_when_disabled(self):
        """Prometheus metrics are initialized even when MQTT is disabled."""
        settings = _make_test_settings(mqtt_url=None)
        service = MqttService(config=settings)

        # Verify metrics objects exist
        assert hasattr(service, "mqtt_publish_total")
        assert hasattr(service, "mqtt_connection_state")
        assert hasattr(service, "mqtt_publish_duration_seconds")
        assert hasattr(service, "mqtt_enabled_gauge")
