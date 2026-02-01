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

        # Image proxy metrics
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

        # Authentication metrics
        self.auth_validation_total = Counter(
            "iot_auth_validation_total",
            "Total JWT token validation attempts",
            ["status"],
        )

        self.auth_validation_duration_seconds = Histogram(
            "iot_auth_validation_duration_seconds",
            "Duration of JWT token validation in seconds",
        )

        self.jwks_refresh_total = Counter(
            "iot_jwks_refresh_total",
            "Total JWKS refresh attempts",
            ["trigger", "status"],
        )

        self.oidc_token_exchange_total = Counter(
            "iot_oidc_token_exchange_total",
            "Total OIDC token exchange attempts",
            ["status"],
        )

        self.auth_token_refresh_total = Counter(
            "iot_auth_token_refresh_total",
            "Total access token refresh attempts",
            ["status"],
        )

        # Elasticsearch metrics
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

    def record_image_proxy_operation(
        self,
        status: str | None,
        error_type: str | None,
        operation_duration: float | None = None,
        fetch_duration: float | None = None,
        image_size: int | None = None,
    ) -> None:
        """Record an image proxy operation.

        Args:
            status: Operation status (success, error), or None to skip counter
            error_type: Type of error (missing_param, external_fetch_failed, etc., or none for success), or None to skip counter
            operation_duration: Total operation duration in seconds (optional)
            fetch_duration: External fetch duration in seconds (optional)
            image_size: Size of fetched image in bytes (optional)
        """
        try:
            # Only increment counter if status and error_type are provided (API layer)
            # Service layer can record granular metrics without incrementing overall counter
            if status is not None and error_type is not None:
                self.image_proxy_operations_total.labels(
                    status=status, error_type=error_type
                ).inc()

            if operation_duration is not None:
                self.image_proxy_operation_duration_seconds.observe(operation_duration)

            if fetch_duration is not None:
                self.image_proxy_external_fetch_duration_seconds.observe(
                    fetch_duration
                )

            if image_size is not None:
                self.image_proxy_image_size_bytes.observe(image_size)
        except Exception as e:
            logger.error("Error recording image proxy metric: %s", e)

    def increment_counter(self, metric_name: str, labels: dict[str, str] | None = None) -> None:
        """Increment a counter metric by name.

        Generic method for incrementing any counter metric.

        Args:
            metric_name: Name of the counter metric (e.g., 'iot_auth_validation_total')
            labels: Optional dictionary of label names and values
        """
        try:
            metric = getattr(self, metric_name.replace("iot_", ""), None)
            if metric and hasattr(metric, "labels"):
                if labels:
                    metric.labels(**labels).inc()
                else:
                    metric.inc()
        except Exception as e:
            logger.error("Error incrementing counter %s: %s", metric_name, e)

    def record_operation_duration(self, metric_name: str, duration: float) -> None:
        """Record a duration observation for a histogram metric.

        Generic method for recording durations.

        Args:
            metric_name: Name of the histogram metric (e.g., 'iot_auth_validation_duration_seconds')
            duration: Duration in seconds
        """
        try:
            metric = getattr(self, metric_name.replace("iot_", ""), None)
            if metric and hasattr(metric, "observe"):
                metric.observe(duration)
        except Exception as e:
            logger.error("Error recording duration for %s: %s", metric_name, e)

    def get_metrics_text(self) -> str:
        """Generate metrics in Prometheus text format.

        Returns:
            Metrics data in Prometheus exposition format
        """
        return generate_latest().decode("utf-8")
