"""Prometheus metrics service for collecting and exposing application metrics."""

import logging

from prometheus_client import Counter, Gauge, Histogram, generate_latest

logger = logging.getLogger(__name__)


class MetricsService:
    """Service class for Prometheus metrics collection and exposure.

    Unlike ElectronicsInventory, this service has no background polling thread
    since there's no database to query. All metrics are updated on-demand
    during API operations.
    """

    def __init__(self) -> None:
        """Initialize service with metric objects."""
        self.initialize_metrics()

    def initialize_metrics(self) -> None:
        """Define all Prometheus metric objects."""
        # Check if already initialized (for container singleton reuse)
        if hasattr(self, "config_operations_total"):
            return

        # Config operation metrics
        self.config_operations_total = Counter(
            "iot_config_operations_total",
            "Total configuration operations",
            ["operation", "status"],
        )

        self.config_files_count = Gauge(
            "iot_config_files_count", "Current number of configuration files"
        )

        self.config_operation_duration_seconds = Histogram(
            "iot_config_operation_duration_seconds",
            "Duration of configuration operations in seconds",
            ["operation"],
        )

    def record_operation(
        self, operation: str, status: str, duration: float | None = None
    ) -> None:
        """Record a configuration operation.

        Args:
            operation: Operation type (list, get, save, delete)
            status: Status (success, error)
            duration: Operation duration in seconds (optional)
        """
        try:
            self.config_operations_total.labels(
                operation=operation, status=status
            ).inc()

            if duration is not None:
                self.config_operation_duration_seconds.labels(operation=operation).observe(
                    duration
                )
        except Exception as e:
            logger.error("Error recording operation metric: %s", e)

    def update_config_count(self, count: int) -> None:
        """Update the current config file count gauge.

        Args:
            count: Current number of config files
        """
        try:
            self.config_files_count.set(count)
        except Exception as e:
            logger.error("Error updating config count metric: %s", e)

    def get_metrics_text(self) -> str:
        """Generate metrics in Prometheus text format.

        Returns:
            Metrics data in Prometheus exposition format
        """
        return generate_latest().decode("utf-8")
