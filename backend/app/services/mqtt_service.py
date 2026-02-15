"""MQTT service for publishing and subscribing to MQTT messages.

This is a singleton service that maintains a single persistent MQTT v5 connection
to a broker. It supports both publishing (fire-and-forget notifications) and
subscribing (with message callbacks).
"""

import atexit
import logging
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from paho.mqtt.client import Client as MqttClient
from paho.mqtt.client import ConnectFlags, DisconnectFlags, MQTTMessage
from paho.mqtt.enums import CallbackAPIVersion, MQTTProtocolVersion
from paho.mqtt.packettypes import PacketTypes
from paho.mqtt.properties import Properties
from paho.mqtt.reasoncodes import ReasonCode
from prometheus_client import Counter, Gauge, Histogram

from app.utils.mqtt import parse_mqtt_url

if TYPE_CHECKING:
    from app.app_config import AppSettings

logger = logging.getLogger(__name__)

# Type alias for subscription callbacks
MessageCallback = Callable[[bytes], None]


class MqttService:
    """Singleton MQTT service for publish and subscribe operations.

    This service maintains a single persistent MQTT v5 connection to a broker.
    It supports:
    - Publishing fire-and-forget notifications
    - Subscribing to topics with message callbacks

    The service uses persistent sessions (clean_start=False) so the broker
    queues messages while the client is disconnected.

    The service is optional - if MQTT_URL is not configured, all operations
    silently skip without errors.
    """

    # Root topic for update notifications
    TOPIC_UPDATES = "iotsupport/updates"

    def __init__(
        self,
        config: "AppSettings",
    ) -> None:
        """Initialize MQTT service state without connecting.

        Connection is deferred to startup() which is called by the container's
        start_background_services(). This prevents MQTT connections in CLI
        commands, tests, and the Flask reloader parent process.

        Args:
            config: Application settings with MQTT configuration
        """
        self.config = config

        # Track whether MQTT is enabled
        self.enabled = False
        self.client: MqttClient | None = None
        self._shutdown_called = False

        # Subscription callbacks: topic -> (qos, callback function)
        self._subscriptions: dict[str, tuple[int, MessageCallback]] = {}

        # Buffer for messages that arrive before callbacks are registered.
        # This handles the race condition with persistent sessions where Mosquitto
        # delivers queued messages immediately on reconnect, before other services
        # have registered their subscription callbacks.
        self._pending_messages: dict[str, list[bytes]] = {}

        # Initialize Prometheus metrics
        self._initialize_metrics()

    def startup(self) -> None:
        """Connect to the MQTT broker and start the network loop.

        This is called by the container's start_background_services() and
        should not be called directly. It is idempotent.
        """
        # Already connected (or no URL configured)
        if self.client is not None:
            return

        if not self.config.mqtt_url:
            logger.info("MQTT not configured (MQTT_URL is None), skipping connection")
            self.mqtt_enabled_gauge.set(0)
            return

        # Parse broker URL to extract host and port
        try:
            host, port, use_tls = parse_mqtt_url(self.config.mqtt_url)
        except Exception as e:
            logger.error("Failed to parse MQTT_URL '%s': %s", self.config.mqtt_url, e)
            self.mqtt_enabled_gauge.set(0)
            return

        # Create MQTT client with v5 protocol and persistent session
        try:
            self.client = MqttClient(
                callback_api_version=CallbackAPIVersion.VERSION2,
                protocol=MQTTProtocolVersion.MQTTv5,
                client_id=self.config.mqtt_client_id,
            )

            # Set credentials if provided
            if self.config.mqtt_username and self.config.mqtt_password:
                self.client.username_pw_set(self.config.mqtt_username, self.config.mqtt_password)

            # Configure TLS if using mqtts://
            if use_tls:
                self.client.tls_set()

            # Register callbacks for connection events
            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect
            self.client.on_message = self._on_message

            # Start asynchronous connection with clean_start=False for persistent session
            logger.info(
                "Connecting to MQTT broker at %s:%d with client_id=%s",
                host,
                port,
                self.config.mqtt_client_id,
            )

            # Set session expiry interval for persistent sessions (MQTT v5).
            # This tells the broker to keep the session alive for this many seconds
            # after disconnect, queuing messages for QoS > 0 subscriptions.
            # 1 hour = 3600 seconds - long enough to survive restarts/deployments.
            connect_properties = Properties(PacketTypes.CONNECT)
            connect_properties.SessionExpiryInterval = 3600

            self.client.connect_async(
                host, port, clean_start=False, properties=connect_properties
            )
            self.client.loop_start()

            # Note: enabled will be set to True in _on_connect callback when
            # connection is confirmed. This prevents publish attempts during
            # the async connection establishment window.
            self.mqtt_enabled_gauge.set(1)

            # Register shutdown handler for clean disconnect
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

        self.mqtt_subscriptions_total = Gauge(
            "iot_mqtt_subscriptions_total",
            "Number of active MQTT subscriptions",
        )

        # Initialize gauges
        self.mqtt_connection_state.set(0)
        self.mqtt_enabled_gauge.set(0)
        self.mqtt_subscriptions_total.set(0)

    def _on_connect(
        self,
        client: MqttClient,
        userdata: Any,
        connect_flags: ConnectFlags,
        reason_code: ReasonCode,
        properties: Any,
    ) -> None:
        """Callback when MQTT client connects to broker.

        Re-subscribes to all registered topics on reconnect.
        """
        if reason_code.is_failure:
            logger.error("Failed to connect to MQTT broker: %s", reason_code)
            self.mqtt_connection_state.set(0)
            # Disable publishing on connection failure
            self.enabled = False
        else:
            logger.info("Connected to MQTT broker successfully")
            self.mqtt_connection_state.set(1)
            # Enable publishing now that connection is confirmed
            self.enabled = True

            # Re-subscribe to all registered topics
            for topic, (qos, _callback) in self._subscriptions.items():
                client.subscribe(topic, qos=qos)
                logger.info("Subscribed to MQTT topic: %s (QoS %d)", topic, qos)

    def _on_disconnect(
        self,
        client: MqttClient,
        userdata: Any,
        disconnect_flags: DisconnectFlags,
        reason_code: ReasonCode,
        properties: Any,
    ) -> None:
        """Callback when MQTT client disconnects from broker."""
        logger.warning("Disconnected from MQTT broker: %s", reason_code)
        self.mqtt_connection_state.set(0)
        # paho-mqtt will automatically reconnect

    def _on_message(
        self,
        client: MqttClient,
        userdata: Any,
        message: MQTTMessage,
    ) -> None:
        """Callback when a message is received on a subscribed topic.

        Routes the message to the registered callback for the topic.
        If no callback is registered yet (race condition with persistent sessions),
        buffers the message for delivery when the callback is registered.
        """
        topic = message.topic
        callback_info = self._subscriptions.get(topic)

        if callback_info is None:
            # Buffer the message - this handles the race condition where persistent
            # session messages arrive before the subscribing service registers its callback
            if topic not in self._pending_messages:
                self._pending_messages[topic] = []
            self._pending_messages[topic].append(message.payload)
            logger.debug(
                "Buffered message on topic %s (no callback registered yet, %d pending)",
                topic,
                len(self._pending_messages[topic]),
            )
            return

        _qos, callback = callback_info
        try:
            callback(message.payload)
        except Exception as e:
            logger.error("Error in message callback for topic %s: %s", topic, e)

    def subscribe(
        self,
        topic: str,
        qos: int,
        callback: MessageCallback,
    ) -> None:
        """Subscribe to an MQTT topic with a message callback.

        The callback will be invoked with the raw payload bytes whenever a
        message is received on the topic. If already connected, the subscription
        happens immediately; otherwise it will be established on connect.

        Any messages that were buffered (due to arriving before this callback
        was registered) will be delivered immediately.

        Args:
            topic: MQTT topic to subscribe to
            qos: Quality of Service level (0, 1, or 2)
            callback: Function to call with message payload bytes
        """
        # Store subscription for reconnect
        self._subscriptions[topic] = (qos, callback)
        self.mqtt_subscriptions_total.set(len(self._subscriptions))

        # Deliver any buffered messages that arrived before this callback was registered
        pending = self._pending_messages.pop(topic, [])
        if pending:
            logger.info(
                "Delivering %d buffered messages for topic %s", len(pending), topic
            )
            for payload in pending:
                try:
                    callback(payload)
                except Exception as e:
                    logger.error(
                        "Error delivering buffered message for topic %s: %s", topic, e
                    )

        # Subscribe immediately if connected
        if self.enabled and self.client is not None:
            self.client.subscribe(topic, qos=qos)
            logger.info("Subscribed to MQTT topic: %s (QoS %d)", topic, qos)
        else:
            logger.info(
                "Queued subscription for MQTT topic: %s (QoS %d) - will subscribe on connect",
                topic,
                qos,
            )

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
                # Disconnect first to send DISCONNECT packet to broker
                self.client.disconnect()
                # Small delay to allow the disconnect packet to be sent
                time.sleep(0.1)
                # Then stop the network loop
                self.client.loop_stop()
                self.mqtt_connection_state.set(0)
                logger.info("MQTT service shutdown complete")
            except Exception as e:
                logger.error("Error during MQTT shutdown: %s", e)
