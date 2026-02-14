"""MQTT log sink service for ingesting device logs to Elasticsearch.

This service subscribes to an MQTT topic for device logs, processes incoming
messages (strips ANSI codes, adds timestamps), and batches them for writing
to Elasticsearch via the _bulk API with exponential backoff retry.
"""

import json
import logging
import threading
import time
from datetime import UTC, datetime
from queue import Empty, Queue, ShutDown  # type: ignore[attr-defined]
from typing import TYPE_CHECKING, Any

import httpx
from prometheus_client import Counter, Gauge, Histogram

from app.utils.ansi import strip_ansi
from app.utils.lifecycle_coordinator import LifecycleCoordinatorProtocol, LifecycleEvent

if TYPE_CHECKING:
    from app.app_config import AppSettings
    from app.services.mqtt_service import MqttService

logger = logging.getLogger(__name__)


class LogSinkService:
    """Service for subscribing to MQTT log messages and writing to Elasticsearch.

    This service subscribes to the log sink MQTT topic via the shared MqttService,
    processes incoming messages (strips ANSI codes, adds timestamps), enqueues them,
    and a background writer thread batches documents via the ES _bulk API.

    The service is optional - it only activates when both MQTT and Elasticsearch
    are configured.
    """

    # MQTT topic for log messages
    LOGSINK_TOPIC = "iotsupport/logsink"

    # Queue and batch configuration
    QUEUE_MAXSIZE = 100

    # Retry configuration
    INITIAL_RETRY_DELAY = 1.0  # seconds
    RETRY_DELAY_INCREMENT = 1.0  # seconds
    MAX_RETRY_DELAY = 60.0  # seconds

    def __init__(
        self,
        config: "AppSettings",
        mqtt_service: "MqttService",
        lifecycle_coordinator: LifecycleCoordinatorProtocol,
    ) -> None:
        """Initialize log sink service.

        Args:
            config: Application settings with Elasticsearch configuration
            mqtt_service: Shared MQTT service for subscription
            lifecycle_coordinator: Lifecycle coordinator for startup/shutdown
        """
        self.config = config
        self.mqtt_service = mqtt_service
        self._lifecycle_coordinator = lifecycle_coordinator

        # Track service state
        self.enabled = False
        self._http_client: httpx.Client | None = None
        self._queue: Queue[tuple[str, dict[str, Any]]] = Queue(maxsize=self.QUEUE_MAXSIZE)
        self._writer_thread: threading.Thread | None = None

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

        # Register with lifecycle coordinator
        lifecycle_coordinator.register_lifecycle_notification(self._on_lifecycle_event)
        lifecycle_coordinator.register_shutdown_waiter("LogSinkService", self._wait_for_shutdown)

        # Start background writer thread
        self._writer_thread = threading.Thread(
            target=self._writer_loop,
            name="logsink-writer",
            daemon=True,
        )
        self._writer_thread.start()

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
            "Total Elasticsearch bulk write attempts",
            ["status", "error_type"],
        )

        self.logsink_es_write_duration_seconds = Histogram(
            "iot_logsink_es_write_duration_seconds",
            "Duration of successful Elasticsearch bulk writes in seconds",
        )

        self.logsink_retry_delay_seconds = Gauge(
            "iot_logsink_retry_delay_seconds",
            "Current retry backoff delay in seconds (0 when not retrying)",
        )

        self.logsink_enabled_gauge = Gauge(
            "iot_logsink_enabled",
            "LogSink service enabled state (0=disabled, 1=enabled)",
        )

        self.logsink_batch_size = Histogram(
            "iot_logsink_batch_size",
            "Number of documents per bulk request",
        )

        self.logsink_queue_depth = Gauge(
            "iot_logsink_queue_depth",
            "Current number of items in the write queue",
        )

        # Initialize gauges
        self.logsink_enabled_gauge.set(0)
        self.logsink_retry_delay_seconds.set(0)
        self.logsink_queue_depth.set(0)

    def _on_message(self, payload: bytes) -> None:
        """Callback when a message is received on the log sink topic.

        Processes the message as NDJSON (newline-delimited JSON) and enqueues
        each document for batch writing to Elasticsearch.
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
            except ShutDown:
                # Queue has been shut down — service is stopping
                logger.info("LogSinkService queue shut down, dropping message")
                return
            except Exception as e:
                # Processing error - log but continue to next line
                logger.error("LogSinkService error processing message: %s", e)
                self.logsink_messages_received_total.labels(
                    status="processing_error"
                ).inc()

    def _process_line(self, line: str) -> None:
        """Process a single NDJSON line and enqueue for batch writing.

        Args:
            line: Single JSON line from NDJSON payload

        Raises:
            json.JSONDecodeError: If line is not valid JSON
            ShutDown: If the queue has been shut down
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

        # Compute target index name at enqueue time so midnight boundaries
        # are handled correctly
        index_date = datetime.now(UTC).strftime("%Y.%m.%d")
        index_name = f"logstash-http-{index_date}"

        # Enqueue for batch writing (blocks if queue is full)
        self._queue.put((index_name, data))
        self.logsink_queue_depth.set(self._queue.qsize())

    def _writer_loop(self) -> None:
        """Background writer thread that drains the queue and writes batches to ES."""
        while True:
            try:
                first = self._queue.get()
            except ShutDown:
                # Queue has been shut down and drained
                break

            # Drain up to maxsize items into a batch
            batch = [first]
            for _ in range(self._queue.maxsize - 1):
                try:
                    batch.append(self._queue.get_nowait())
                except (Empty, ShutDown):
                    break

            self.logsink_queue_depth.set(self._queue.qsize())
            self._write_batch_to_elasticsearch(batch)

        logger.info("LogSinkService writer thread exiting")

    def _write_batch_to_elasticsearch(
        self, batch: list[tuple[str, dict[str, Any]]]
    ) -> None:
        """Write a batch of documents to Elasticsearch via the _bulk API.

        Retries with exponential backoff until successful or shutdown is requested.

        Args:
            batch: List of (index_name, document) tuples to write
        """
        if self._http_client is None:
            logger.error("LogSinkService HTTP client not initialized")
            return

        # Build NDJSON bulk body
        bulk_lines: list[str] = []
        for index_name, document in batch:
            action = json.dumps({"index": {"_index": index_name}})
            doc = json.dumps(document)
            bulk_lines.append(action)
            bulk_lines.append(doc)

        # _bulk API requires trailing newline
        bulk_body = "\n".join(bulk_lines) + "\n"

        delay = self.INITIAL_RETRY_DELAY
        attempt = 0

        # Always attempt at least the first write (even during shutdown drain).
        # The shutdown check gates only retries, so queued items being drained
        # still get one write attempt.
        while True:
            attempt += 1
            start_time = time.perf_counter()

            try:
                url = f"{self.config.elasticsearch_url}/_bulk"
                auth = self._get_es_auth()

                response = self._http_client.post(
                    url,
                    content=bulk_body,
                    auth=auth,  # type: ignore[arg-type]
                    headers={"Content-Type": "application/x-ndjson"},
                )
                response.raise_for_status()

                # Success
                duration = time.perf_counter() - start_time
                self.logsink_es_write_duration_seconds.observe(duration)
                self.logsink_es_writes_total.labels(
                    status="success", error_type="none"
                ).inc()
                self.logsink_batch_size.observe(len(batch))
                self.logsink_retry_delay_seconds.set(0)

                if attempt > 1:
                    logger.info(
                        "LogSinkService ES bulk write succeeded after %d attempts "
                        "(%.3fs, %d docs)",
                        attempt,
                        duration,
                        len(batch),
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

            # Abort retry if shutting down — accept data loss for items stuck
            # in the retry loop during forced shutdown
            if self._lifecycle_coordinator.is_shutting_down():
                logger.info(
                    "LogSinkService shutdown during ES retry, aborting (%d docs)",
                    len(batch),
                )
                return

            # Update retry delay gauge and wait
            self.logsink_retry_delay_seconds.set(delay)
            logger.debug("LogSinkService retrying in %.1fs", delay)

            # Sleep with periodic shutdown checks for interruptibility
            sleep_end = time.perf_counter() + delay
            while time.perf_counter() < sleep_end:
                if self._lifecycle_coordinator.is_shutting_down():
                    logger.info("LogSinkService shutdown during ES retry wait, aborting")
                    return
                time.sleep(min(0.1, sleep_end - time.perf_counter()))

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

    def _on_lifecycle_event(self, event: LifecycleEvent) -> None:
        """Handle lifecycle events from the coordinator."""
        match event:
            case LifecycleEvent.PREPARE_SHUTDOWN:
                # Shut down the queue: producers get ShutDown, consumer drains
                logger.info("LogSinkService: PREPARE_SHUTDOWN - shutting down queue")
                self._queue.shutdown(immediate=False)  # type: ignore[attr-defined]
            case LifecycleEvent.SHUTDOWN:
                # Close HTTP client
                if self._http_client is not None:
                    try:
                        logger.info("LogSinkService: SHUTDOWN - closing HTTP client")
                        self._http_client.close()
                    except Exception as e:
                        logger.error("Error closing LogSinkService HTTP client: %s", e)

    def _wait_for_shutdown(self, timeout: float) -> bool:
        """Wait for the writer thread to finish draining the queue.

        Args:
            timeout: Maximum seconds to wait

        Returns:
            True if the writer thread finished, False if timeout exceeded
        """
        if self._writer_thread is not None:
            self._writer_thread.join(timeout=timeout)
            return not self._writer_thread.is_alive()
        return True
