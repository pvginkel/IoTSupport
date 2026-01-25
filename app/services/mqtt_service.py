"""MQTT notification service for publishing device update notifications."""

import atexit
import logging
import time
from typing import Any

from paho.mqtt.client import Client as MqttClient
from paho.mqtt.client import ConnectFlags, DisconnectFlags
from paho.mqtt.enums import CallbackAPIVersion, MQTTProtocolVersion
from paho.mqtt.reasoncodes import ReasonCode
from prometheus_client import Counter, Gauge, Histogram

logger = logging.getLogger(__name__)


class MqttService:
    """Service for publishing MQTT notifications about config and asset updates.

    This is a singleton service that maintains a persistent MQTT v5 connection
    to a broker. It publishes fire-and-forget notifications when configs are saved
    or assets are uploaded, allowing IoT devices to subscribe and receive immediate
    update notifications instead of polling.

    The service is optional - if MQTT_URL is not configured, all publish operations
    silently skip without errors.
    """

    # Root topic for update notifications
    TOPIC_UPDATES = "iotsupport/updates"

    def __init__(
        self,
        mqtt_url: str | None = None,
        mqtt_username: str | None = None,
        mqtt_password: str | None = None,
    ) -> None:
        """Initialize MQTT service with optional broker connection.

        Args:
            mqtt_url: MQTT broker URL (e.g., mqtt://localhost:1883, mqtts://broker:8883)
            mqtt_username: MQTT broker username (optional)
            mqtt_password: MQTT broker password (optional)
        """
        # Track whether MQTT is enabled
        self.enabled = False
        self.client: MqttClient | None = None
        self._shutdown_called = False

        # Initialize Prometheus metrics
        self._initialize_metrics()

        # Skip connection if MQTT_URL not configured
        if not mqtt_url:
            logger.info("MQTT not configured (MQTT_URL is None), skipping connection")
            self.mqtt_enabled_gauge.set(0)
            return

        # Parse broker URL to extract host and port
        try:
            host, port, use_tls = self._parse_mqtt_url(mqtt_url)
        except Exception as e:
            logger.error("Failed to parse MQTT_URL '%s': %s", mqtt_url, e)
            self.mqtt_enabled_gauge.set(0)
            return

        # Create MQTT client with v5 protocol
        try:
            self.client = MqttClient(
                callback_api_version=CallbackAPIVersion.VERSION2,
                protocol=MQTTProtocolVersion.MQTTv5,
            )

            # Set credentials if provided
            if mqtt_username and mqtt_password:
                self.client.username_pw_set(mqtt_username, mqtt_password)

            # Configure TLS if using mqtts://
            if use_tls:
                self.client.tls_set()

            # Register callbacks for connection events
            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect

            # Start asynchronous connection
            logger.info("Connecting to MQTT broker at %s:%d", host, port)
            self.client.connect_async(host, port)
            self.client.loop_start()

            # Note: enabled will be set to True in _on_connect callback when
            # connection is confirmed. This prevents publish attempts during
            # the async connection establishment window.
            self.mqtt_enabled_gauge.set(1)

            # Register shutdown handler
            atexit.register(self.shutdown)

        except Exception as e:
            logger.error("Failed to initialize MQTT client: %s", e)
            self.enabled = False
            self.mqtt_enabled_gauge.set(0)

    def _initialize_metrics(self) -> None:
        """Initialize Prometheus metrics for MQTT operations."""
        # Check if already initialized (for container singleton reuse)
        if hasattr(self, "mqtt_publish_total"):
            return

        self.mqtt_publish_total = Counter(
            "iot_mqtt_publish_total",
            "Total MQTT publish attempts",
            ["topic", "status"],
        )

        self.mqtt_connection_state = Gauge(
            "iot_mqtt_connection_state",
            "MQTT connection state (0=disconnected, 1=connected)",
        )

        self.mqtt_publish_duration_seconds = Histogram(
            "iot_mqtt_publish_duration_seconds",
            "Duration of MQTT publish operations in seconds",
            ["topic"],
        )

        self.mqtt_enabled_gauge = Gauge(
            "iot_mqtt_enabled",
            "MQTT service enabled state (0=disabled, 1=enabled)",
        )

        # Initialize connection state to disconnected
        self.mqtt_connection_state.set(0)
        self.mqtt_enabled_gauge.set(0)

    def _parse_mqtt_url(self, url: str) -> tuple[str, int, bool]:
        """Parse MQTT URL to extract host, port, and TLS settings.

        Args:
            url: MQTT URL (e.g., mqtt://localhost:1883, mqtts://broker:8883)

        Returns:
            Tuple of (host, port, use_tls)

        Raises:
            ValueError: If URL format is invalid
        """
        if url.startswith("mqtts://"):
            use_tls = True
            url_without_scheme = url[8:]
            default_port = 8883
        elif url.startswith("mqtt://"):
            use_tls = False
            url_without_scheme = url[7:]
            default_port = 1883
        else:
            raise ValueError(
                f"Invalid MQTT URL scheme. Expected mqtt:// or mqtts://, got: {url}"
            )

        # Split host and port
        if ":" in url_without_scheme:
            host, port_str = url_without_scheme.split(":", 1)
            # Remove any trailing path components
            port_str = port_str.split("/")[0]
            port = int(port_str)
        else:
            # Remove any trailing path components
            host = url_without_scheme.split("/")[0]
            port = default_port

        return (host, port, use_tls)

    def _on_connect(
        self,
        client: MqttClient,
        userdata: Any,
        connect_flags: ConnectFlags,
        reason_code: ReasonCode,
        properties: Any,
    ) -> None:
        """Callback when MQTT client connects to broker.

        Args:
            client: MQTT client instance
            userdata: User data (unused)
            connect_flags: Connection flags
            reason_code: Connection result code
            properties: MQTT v5 properties
        """
        if reason_code.is_failure:
            logger.error(
                "Failed to connect to MQTT broker: %s", reason_code
            )
            self.mqtt_connection_state.set(0)
            # Disable publishing on connection failure
            self.enabled = False
        else:
            logger.info("Connected to MQTT broker successfully")
            self.mqtt_connection_state.set(1)
            # Enable publishing now that connection is confirmed
            self.enabled = True

    def _on_disconnect(
        self,
        client: MqttClient,
        userdata: Any,
        disconnect_flags: DisconnectFlags,
        reason_code: ReasonCode,
        properties: Any,
    ) -> None:
        """Callback when MQTT client disconnects from broker.

        Args:
            client: MQTT client instance
            userdata: User data (unused)
            disconnect_flags: Disconnect flags
            reason_code: Disconnection reason code
            properties: MQTT v5 properties
        """
        logger.warning("Disconnected from MQTT broker: %s", reason_code)
        self.mqtt_connection_state.set(0)
        # paho-mqtt will automatically reconnect

    def publish(self, topic: str, payload: str) -> None:
        """Publish an MQTT message.

        This is a fire-and-forget operation. Errors are logged but not raised.

        Args:
            topic: MQTT topic to publish to
            payload: Plain text payload to send
        """
        # Skip if MQTT is disabled
        if not self.enabled or self.client is None:
            return

        start_time = time.perf_counter()

        try:
            # Publish with QoS 1, no retain
            result = self.client.publish(topic, payload, qos=1, retain=False)

            # Check if publish was queued successfully
            if result.rc == 0:
                self.mqtt_publish_total.labels(topic=topic, status="success").inc()
            else:
                logger.warning(
                    "MQTT publish failed for topic '%s', payload '%s': return code %d",
                    topic,
                    payload,
                    result.rc,
                )
                self.mqtt_publish_total.labels(topic=topic, status="failure").inc()

        except Exception as e:
            # Log error but don't raise (fire-and-forget)
            logger.error(
                "Exception during MQTT publish to topic '%s', payload '%s': %s",
                topic,
                payload,
                e,
            )
            self.mqtt_publish_total.labels(topic=topic, status="failure").inc()

        finally:
            duration = time.perf_counter() - start_time
            self.mqtt_publish_duration_seconds.labels(topic=topic).observe(duration)

    def shutdown(self) -> None:
        """Gracefully shutdown MQTT connection.

        Stops the network loop and disconnects from broker. This method is
        idempotent and safe to call multiple times.
        """
        # Prevent multiple shutdowns
        if self._shutdown_called:
            return

        self._shutdown_called = True

        if self.client is not None:
            try:
                logger.info("Shutting down MQTT service")
                self.client.loop_stop()
                self.client.disconnect()
                self.mqtt_connection_state.set(0)
            except Exception as e:
                logger.error("Error during MQTT shutdown: %s", e)
