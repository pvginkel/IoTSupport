"""MQTT log sink service for ingesting device logs to Elasticsearch.

This service subscribes to an MQTT topic for device logs, processes incoming
messages (strips ANSI codes, adds timestamps), and writes them to Elasticsearch
with exponential backoff retry.
"""

import json
import logging
import threading
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import httpx
from prometheus_client import Counter, Gauge, Histogram

from app.utils.ansi import strip_ansi

if TYPE_CHECKING:
    from app.config import Settings
    from app.services.mqtt_service import MqttService

logger = logging.getLogger(__name__)


class LogSinkService:
    """Service for subscribing to MQTT log messages and writing to Elasticsearch.

    This service subscribes to the log sink MQTT topic via the shared MqttService,
    processes incoming messages (strips ANSI codes, adds timestamps), and writes
    them to Elasticsearch with exponential backoff retry.

    The service is optional - it only activates when both MQTT and Elasticsearch
    are configured.
    """

    # MQTT topic for log messages
    LOGSINK_TOPIC = "iotsupport/logsink"

    # Retry configuration
    INITIAL_RETRY_DELAY = 1.0  # seconds
    RETRY_DELAY_INCREMENT = 1.0  # seconds
    MAX_RETRY_DELAY = 60.0  # seconds

    def __init__(
        self,
        config: "Settings",
        mqtt_service: "MqttService",
    ) -> None:
        """Initialize log sink service.

        Args:
            config: Application settings with Elasticsearch configuration
            mqtt_service: Shared MQTT service for subscription
        """
        self.config = config
        self.mqtt_service = mqtt_service

        # Track service state
        self.enabled = False
        self._shutdown_event = threading.Event()
        self._http_client: httpx.Client | None = None

        # Initialize Prometheus metrics
        self._initialize_metrics()

        # Check if MQTT service is available
        if not mqtt_service.config.mqtt_url:
            logger.info("LogSinkService disabled: MQTT not configured")
            self.logsink_enabled_gauge.set(0)
            return

        # Check if Elasticsearch is configured
        if not config.elasticsearch_url:
            logger.info("LogSinkService disabled: ELASTICSEARCH_URL not configured")
            self.logsink_enabled_gauge.set(0)
            return

        # Initialize HTTP client for Elasticsearch
        self._http_client = httpx.Client(timeout=30.0)

        # Subscribe to log sink topic via shared MQTT service
        mqtt_service.subscribe(
            topic=self.LOGSINK_TOPIC,
            qos=1,
            callback=self._on_message,
        )

        self.enabled = True
        self.logsink_enabled_gauge.set(1)
        logger.info(
            "LogSinkService enabled - subscribed to %s via shared MQTT client",
            self.LOGSINK_TOPIC,
        )

    def _initialize_metrics(self) -> None:
        """Initialize Prometheus metrics for log sink operations."""
        # Check if already initialized (for container singleton reuse)
        if hasattr(self, "logsink_messages_received_total"):
            return

        self.logsink_messages_received_total = Counter(
            "iot_logsink_messages_received_total",
            "Total log messages received from MQTT",
            ["status"],
        )

        self.logsink_es_writes_total = Counter(
            "iot_logsink_es_writes_total",
            "Total Elasticsearch write attempts",
            ["status", "error_type"],
        )

        self.logsink_es_write_duration_seconds = Histogram(
            "iot_logsink_es_write_duration_seconds",
            "Duration of successful Elasticsearch writes in seconds",
        )

        self.logsink_retry_delay_seconds = Gauge(
            "iot_logsink_retry_delay_seconds",
            "Current retry backoff delay in seconds (0 when not retrying)",
        )

        self.logsink_enabled_gauge = Gauge(
            "iot_logsink_enabled",
            "LogSink service enabled state (0=disabled, 1=enabled)",
        )

        # Initialize gauges
        self.logsink_enabled_gauge.set(0)
        self.logsink_retry_delay_seconds.set(0)

    def _on_message(self, payload: bytes) -> None:
        """Callback when a message is received on the log sink topic.

        Processes the message as NDJSON (newline-delimited JSON) and writes
        each line to Elasticsearch with retry logic.
        """
        text = payload.decode("utf-8")

        # Split by newlines and process each non-empty line
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue

            try:
                self._process_line(line)
                self.logsink_messages_received_total.labels(status="success").inc()
            except json.JSONDecodeError as e:
                # Invalid JSON - log and skip this line
                logger.warning(
                    "LogSinkService received invalid JSON: %s (line preview: %.100s)",
                    e,
                    line,
                )
                self.logsink_messages_received_total.labels(status="parse_error").inc()
            except Exception as e:
                # Processing error - log but continue to next line
                logger.error("LogSinkService error processing message: %s", e)
                self.logsink_messages_received_total.labels(
                    status="processing_error"
                ).inc()

    def _process_line(self, line: str) -> None:
        """Process a single NDJSON line and write to Elasticsearch.

        Args:
            line: Single JSON line from NDJSON payload

        Raises:
            json.JSONDecodeError: If line is not valid JSON
        """
        # Parse JSON line
        data = json.loads(line)

        # Strip ANSI codes from message field
        message = data.get("message", "")
        if message:
            data["message"] = strip_ansi(message)

        # Set @timestamp to current UTC time
        data["@timestamp"] = datetime.now(UTC).isoformat()

        # Remove relative_time field if present (we use our own timestamp)
        data.pop("relative_time", None)

        # Compute target index name: logstash-http-YYYY.MM.dd
        index_date = datetime.now(UTC).strftime("%Y.%m.%d")
        index_name = f"logstash-http-{index_date}"

        # Write to Elasticsearch with retry
        self._write_to_elasticsearch(index_name, data)

    def _write_to_elasticsearch(self, index: str, document: dict[str, Any]) -> None:
        """Write a document to Elasticsearch with exponential backoff retry.

        Retries indefinitely until successful or shutdown is requested.

        Args:
            index: Target index name
            document: Document to index
        """
        if self._http_client is None:
            logger.error("LogSinkService HTTP client not initialized")
            return

        delay = self.INITIAL_RETRY_DELAY
        attempt = 0

        while not self._shutdown_event.is_set():
            attempt += 1
            start_time = time.perf_counter()

            try:
                url = f"{self.config.elasticsearch_url}/{index}/_doc"
                auth = self._get_es_auth()

                response = self._http_client.post(
                    url,
                    json=document,
                    auth=auth,  # type: ignore[arg-type]
                    headers={"Content-Type": "application/json"},
                )
                response.raise_for_status()

                # Success
                duration = time.perf_counter() - start_time
                self.logsink_es_write_duration_seconds.observe(duration)
                self.logsink_es_writes_total.labels(
                    status="success", error_type="none"
                ).inc()
                self.logsink_retry_delay_seconds.set(0)

                if attempt > 1:
                    logger.info(
                        "LogSinkService ES write succeeded after %d attempts (%.3fs)",
                        attempt,
                        duration,
                    )

                return

            except httpx.ConnectError as e:
                self.logsink_es_writes_total.labels(
                    status="error", error_type="connection"
                ).inc()
                logger.warning(
                    "LogSinkService ES connection error (attempt %d): %s",
                    attempt,
                    e,
                )

            except httpx.TimeoutException as e:
                self.logsink_es_writes_total.labels(
                    status="error", error_type="timeout"
                ).inc()
                logger.warning(
                    "LogSinkService ES timeout (attempt %d): %s",
                    attempt,
                    e,
                )

            except httpx.HTTPStatusError as e:
                self.logsink_es_writes_total.labels(
                    status="error", error_type="http_error"
                ).inc()
                logger.warning(
                    "LogSinkService ES HTTP error %d (attempt %d): %s",
                    e.response.status_code,
                    attempt,
                    e.response.text[:200] if e.response.text else "No body",
                )

            except Exception as e:
                self.logsink_es_writes_total.labels(
                    status="error", error_type="unknown"
                ).inc()
                logger.warning(
                    "LogSinkService ES error (attempt %d): %s",
                    attempt,
                    e,
                )

            # Update retry delay gauge and wait
            self.logsink_retry_delay_seconds.set(delay)
            logger.debug("LogSinkService retrying in %.1fs", delay)

            # Use Event.wait() for interruptible sleep
            if self._shutdown_event.wait(timeout=delay):
                # Shutdown was signaled during wait
                logger.info("LogSinkService shutdown during ES retry, aborting")
                return

            # Increment delay for next attempt (capped at MAX_RETRY_DELAY)
            delay = min(delay + self.RETRY_DELAY_INCREMENT, self.MAX_RETRY_DELAY)

    def _get_es_auth(self) -> tuple[str, str] | None:
        """Get Elasticsearch HTTP Basic Auth credentials if configured.

        Returns:
            Tuple of (username, password) or None if not configured
        """
        if self.config.elasticsearch_username and self.config.elasticsearch_password:
            return (
                self.config.elasticsearch_username,
                self.config.elasticsearch_password,
            )
        return None

    def shutdown(self) -> None:
        """Gracefully shutdown the log sink service.

        Signals the shutdown event to interrupt any retry loops and closes
        the HTTP client. Note: MQTT subscription cleanup is handled by MqttService.
        """
        # Signal shutdown to interrupt retry loops
        self._shutdown_event.set()

        # Close HTTP client
        if self._http_client is not None:
            try:
                logger.info("LogSinkService shutting down")
                self._http_client.close()
            except Exception as e:
                logger.error("Error closing LogSinkService HTTP client: %s", e)
