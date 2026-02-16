"""IoT-specific Prometheus metrics and recording utilities.

Generic API operation metrics used across multiple endpoints.
Service-specific metrics live in their respective service modules.
"""

import logging

from prometheus_client import Counter, Histogram

logger = logging.getLogger(__name__)

# Generic API operation metrics (used by API endpoint handlers)
IOT_CONFIG_OPERATIONS_TOTAL = Counter(
    "iot_config_operations_total",
    "Total configuration operations",
    ["operation", "status"],
)
IOT_CONFIG_OPERATION_DURATION_SECONDS = Histogram(
    "iot_config_operation_duration_seconds",
    "Duration of configuration operations in seconds",
    ["operation"],
)


def record_operation(
    operation: str, status: str, duration: float | None = None
) -> None:
    """Record an API operation metric."""
    try:
        IOT_CONFIG_OPERATIONS_TOTAL.labels(
            operation=operation, status=status
        ).inc()
        if duration is not None:
            IOT_CONFIG_OPERATION_DURATION_SECONDS.labels(
                operation=operation
            ).observe(duration)
    except Exception as e:
        logger.error("Error recording operation metric: %s", e)
