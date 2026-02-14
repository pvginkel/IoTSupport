"""Prometheus metrics polling service for periodic gauge updates.

Also provides domain-specific metric recording methods used by IoT services.
"""

import logging
import threading
from collections.abc import Callable
from typing import TYPE_CHECKING

from prometheus_client import Counter, Gauge, Histogram

from app.utils.lifecycle_coordinator import LifecycleEvent

if TYPE_CHECKING:
    from app.utils.lifecycle_coordinator import LifecycleCoordinatorProtocol

logger = logging.getLogger(__name__)


class MetricsService:
    """Thin background-polling service for periodic metric updates.

    Responsibilities:
    - register_for_polling(name, callback): register a callable to be
      invoked on each tick of the background thread.
    - start_background_updater(interval_seconds): spawn the daemon thread.
    - Shutdown integration via LifecycleCoordinator lifecycle events.

    All Prometheus metric *definitions* and *recording logic* live in the
    services that publish them (module-level Counter / Gauge / Histogram
    objects).  MetricsService does NOT define or wrap any metrics itself.
    """

    def __init__(
        self,
        container: object,
        lifecycle_coordinator: "LifecycleCoordinatorProtocol",
    ) -> None:
        self.container = container
        self.lifecycle_coordinator = lifecycle_coordinator

        # Registered polling callbacks: name -> callable
        self._polling_callbacks: dict[str, Callable[[], None]] = {}

        # Background thread control
        self._stop_event = threading.Event()
        self._updater_thread: threading.Thread | None = None

        # Register for lifecycle notifications
        self.lifecycle_coordinator.register_lifecycle_notification(
            self._on_lifecycle_event
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register_for_polling(
        self, name: str, callback: Callable[[], None]
    ) -> None:
        """Register a callback to be invoked on each background tick.

        Args:
            name: Human-readable identifier (used for logging on error).
            callback: Zero-arg callable executed once per polling interval.
        """
        self._polling_callbacks[name] = callback
        logger.debug("Registered polling callback: %s", name)

    def start_background_updater(self, interval_seconds: int = 60) -> None:
        """Start the daemon thread that invokes registered polling callbacks.

        Args:
            interval_seconds: Seconds between polling ticks.
        """
        if self._updater_thread is not None and self._updater_thread.is_alive():
            return  # Already running

        self._stop_event.clear()
        self._updater_thread = threading.Thread(
            target=self._background_update_loop,
            args=(interval_seconds,),
            daemon=True,
        )
        self._updater_thread.start()

    def shutdown(self) -> None:
        """Stop the background thread.  Safe to call multiple times."""
        self._stop_background_updater()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _stop_background_updater(self) -> None:
        """Signal the background thread to stop and wait for it."""
        self._stop_event.set()
        if self._updater_thread:
            self._updater_thread.join(timeout=5)

    def _background_update_loop(self, interval_seconds: int) -> None:
        """Loop that invokes each registered callback once per tick.

        Waits one full interval before the first tick so that application
        startup (and test fixtures) are not disrupted by concurrent DB
        queries on SQLite.
        """
        while not self._stop_event.is_set():
            # Wait first, then poll — avoids racing with app init / tests
            self._stop_event.wait(interval_seconds)
            if self._stop_event.is_set():
                break

            for name, callback in self._polling_callbacks.items():
                try:
                    callback()
                except Exception as e:
                    logger.error(
                        "Error in polling callback '%s': %s", name, e
                    )

    def _on_lifecycle_event(self, event: LifecycleEvent) -> None:
        """Respond to lifecycle coordinator events."""
        match event:
            case LifecycleEvent.SHUTDOWN:
                self.shutdown()

    # ------------------------------------------------------------------
    # IoT domain metrics
    # ------------------------------------------------------------------

    def _ensure_iot_metrics(self) -> None:
        """Lazily initialize IoT-specific Prometheus metrics."""
        if hasattr(self, "_iot_metrics_initialized"):
            return
        self._iot_metrics_initialized = True

        self.config_operations_total = Counter(
            "iot_config_operations_total",
            "Total configuration operations",
            ["operation", "status"],
        )
        self.config_operation_duration_seconds = Histogram(
            "iot_config_operation_duration_seconds",
            "Duration of configuration operations in seconds",
            ["operation"],
        )
        self.config_files_count = Gauge(
            "iot_config_files_count", "Current number of configuration files"
        )
        self.image_proxy_operations_total = Counter(
            "iot_image_proxy_operations_total",
            "Total image proxy operations",
            ["status", "error_type"],
        )
        self.image_proxy_operation_duration_seconds = Histogram(
            "iot_image_proxy_operation_duration_seconds",
            "Duration of image proxy operations in seconds",
        )
        self.image_proxy_external_fetch_duration_seconds = Histogram(
            "iot_image_proxy_external_fetch_duration_seconds",
            "Duration of external image fetches in seconds",
        )
        self.image_proxy_image_size_bytes = Histogram(
            "iot_image_proxy_image_size_bytes",
            "Size of fetched images in bytes",
        )
        self.elasticsearch_operations_total = Counter(
            "iot_elasticsearch_operations_total",
            "Total Elasticsearch operations",
            ["operation", "status"],
        )
        self.elasticsearch_query_duration_seconds = Histogram(
            "iot_elasticsearch_query_duration_seconds",
            "Duration of Elasticsearch queries in seconds",
            ["operation"],
        )

    def record_operation(
        self, operation: str, status: str, duration: float | None = None
    ) -> None:
        """Record a configuration operation."""
        self._ensure_iot_metrics()
        try:
            self.config_operations_total.labels(
                operation=operation, status=status
            ).inc()
            if duration is not None:
                self.config_operation_duration_seconds.labels(
                    operation=operation
                ).observe(duration)
        except Exception as e:
            logger.error("Error recording operation metric: %s", e)

    def increment_counter(
        self, metric_name: str, labels: dict[str, str] | None = None
    ) -> None:
        """Increment a counter metric by name."""
        self._ensure_iot_metrics()
        try:
            metric = getattr(self, metric_name.replace("iot_", ""), None)
            if metric and hasattr(metric, "labels"):
                if labels:
                    metric.labels(**labels).inc()
                else:
                    metric.inc()
        except Exception as e:
            logger.error("Error incrementing counter %s: %s", metric_name, e)

    def record_elasticsearch_query(
        self, operation: str, duration: float
    ) -> None:
        """Record an Elasticsearch query duration."""
        self._ensure_iot_metrics()
        try:
            self.elasticsearch_query_duration_seconds.labels(
                operation=operation
            ).observe(duration)
        except Exception as e:
            logger.error("Error recording ES query metric: %s", e)

    def record_image_proxy_operation(
        self,
        status: str | None,
        error_type: str | None,
        operation_duration: float | None = None,
        fetch_duration: float | None = None,
        image_size: int | None = None,
    ) -> None:
        """Record an image proxy operation."""
        self._ensure_iot_metrics()
        try:
            if status is not None and error_type is not None:
                self.image_proxy_operations_total.labels(
                    status=status, error_type=error_type
                ).inc()
            if operation_duration is not None:
                self.image_proxy_operation_duration_seconds.observe(operation_duration)
            if fetch_duration is not None:
                self.image_proxy_external_fetch_duration_seconds.observe(fetch_duration)
            if image_size is not None:
                self.image_proxy_image_size_bytes.observe(image_size)
        except Exception as e:
            logger.error("Error recording image proxy metric: %s", e)
