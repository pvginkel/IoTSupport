"""Elasticsearch service for querying device logs."""

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

import httpx

from app.exceptions import ExternalServiceException, ServiceUnavailableException

if TYPE_CHECKING:
    from app.config import Settings
    from app.services.metrics_service import MetricsService

logger = logging.getLogger(__name__)


@dataclass
class LogEntry:
    """Represents a single log entry from Elasticsearch."""

    timestamp: datetime
    message: str


@dataclass
class LogQueryResult:
    """Result of a log query operation."""

    logs: list[LogEntry]
    has_more: bool
    window_start: datetime | None
    window_end: datetime | None


class ElasticsearchService:
    """Service for querying device logs from Elasticsearch.

    This is a singleton service that queries logs from an Elasticsearch cluster.
    It uses httpx for HTTP requests and handles connection errors gracefully.
    """

    # Maximum number of log entries to return per request
    MAX_RESULTS = 1000

    def __init__(
        self,
        config: "Settings",
        metrics_service: "MetricsService",
    ) -> None:
        """Initialize Elasticsearch service.

        Args:
            config: Application settings containing Elasticsearch configuration
            metrics_service: Metrics service for recording operations
        """
        self.config = config
        self.metrics_service = metrics_service

        # HTTP client for API calls with connection pooling
        self._http_client = httpx.Client(timeout=10.0)

        # Check if Elasticsearch is configured
        self.enabled = bool(config.elasticsearch_url)

        if self.enabled:
            logger.info(
                "ElasticsearchService initialized with URL: %s",
                config.elasticsearch_url
            )
        else:
            logger.warning("ElasticsearchService disabled - ELASTICSEARCH_URL not configured")

    def _get_auth(self) -> tuple[str, str] | None:
        """Get HTTP Basic Auth credentials if configured.

        Returns:
            Tuple of (username, password) or None if not configured
        """
        if self.config.elasticsearch_username and self.config.elasticsearch_password:
            return (self.config.elasticsearch_username, self.config.elasticsearch_password)
        return None

    def _record_operation(self, operation: str, status: str) -> None:
        """Record an Elasticsearch operation metric."""
        self.metrics_service.increment_counter(
            "iot_elasticsearch_operations_total",
            labels={"operation": operation, "status": status}
        )

    def _record_duration(self, operation: str, duration: float) -> None:
        """Record Elasticsearch query duration."""
        self.metrics_service.elasticsearch_query_duration_seconds.labels(
            operation=operation
        ).observe(duration)

    def query_logs(
        self,
        entity_id: str | None,
        start: datetime,
        end: datetime,
        query: str | None = None,
    ) -> LogQueryResult:
        """Query device logs from Elasticsearch.

        Args:
            entity_id: Device entity ID to filter by. If None, returns empty result.
            start: Start of time range (inclusive)
            end: End of time range (inclusive)
            query: Optional wildcard query to filter messages

        Returns:
            LogQueryResult with logs, pagination info, and time window

        Raises:
            ServiceUnavailableException: If Elasticsearch is unreachable
            ExternalServiceException: If Elasticsearch returns an error
        """
        # Short-circuit if entity_id is None - return empty result without hitting ES
        if entity_id is None:
            logger.debug("No entity_id provided, returning empty logs")
            return LogQueryResult(
                logs=[],
                has_more=False,
                window_start=None,
                window_end=None,
            )

        if not self.enabled:
            raise ServiceUnavailableException(
                "Elasticsearch",
                "Elasticsearch URL not configured"
            )

        start_time = time.perf_counter()
        status = "success"

        try:
            result = self._execute_query(entity_id, start, end, query)

            duration = time.perf_counter() - start_time
            logger.info(
                "Queried logs for entity_id=%s: %d results, has_more=%s (%.3fs)",
                entity_id,
                len(result.logs),
                result.has_more,
                duration,
            )
            self._record_duration("query_logs", duration)

            return result

        except ServiceUnavailableException:
            status = "error"
            raise

        except ExternalServiceException:
            status = "error"
            raise

        except Exception as e:
            status = "error"
            duration = time.perf_counter() - start_time
            logger.error(
                "Unexpected error querying logs for entity_id=%s: %s (%.3fs)",
                entity_id,
                str(e),
                duration,
            )
            raise ExternalServiceException(
                "query device logs",
                str(e)
            ) from e

        finally:
            self._record_operation("query_logs", status)

    def _execute_query(
        self,
        entity_id: str,
        start: datetime,
        end: datetime,
        query: str | None,
    ) -> LogQueryResult:
        """Execute the Elasticsearch query.

        Args:
            entity_id: Device entity ID to filter by
            start: Start of time range
            end: End of time range
            query: Optional wildcard query for message field

        Returns:
            LogQueryResult with query results
        """
        # Build the Elasticsearch query
        # Request 1 extra to detect if more results exist
        es_query = self._build_query(entity_id, start, end, query)

        url = f"{self.config.elasticsearch_url}/{self.config.elasticsearch_index_pattern}/_search"

        try:
            auth = self._get_auth()
            response = self._http_client.post(
                url,
                json=es_query,
                auth=auth,  # type: ignore[arg-type]
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()

        except httpx.ConnectError as e:
            logger.error("Elasticsearch connection failed: %s", str(e))
            raise ServiceUnavailableException(
                "Elasticsearch",
                "Connection failed"
            ) from e

        except httpx.TimeoutException as e:
            logger.error("Elasticsearch request timed out: %s", str(e))
            raise ServiceUnavailableException(
                "Elasticsearch",
                "Request timed out"
            ) from e

        except httpx.HTTPStatusError as e:
            logger.error(
                "Elasticsearch returned error %d: %s",
                e.response.status_code,
                e.response.text[:500] if e.response.text else "No body"
            )
            raise ExternalServiceException(
                "query device logs",
                f"HTTP {e.response.status_code}"
            ) from e

        except httpx.HTTPError as e:
            logger.error("Elasticsearch HTTP error: %s", str(e))
            raise ExternalServiceException(
                "query device logs",
                str(e)
            ) from e

        # Parse the response
        return self._parse_response(response.json())

    def _build_query(
        self,
        entity_id: str,
        start: datetime,
        end: datetime,
        query: str | None,
    ) -> dict[str, Any]:
        """Build the Elasticsearch query.

        Args:
            entity_id: Device entity ID to filter by
            start: Start of time range
            end: End of time range
            query: Optional wildcard query for message field

        Returns:
            Elasticsearch query dict
        """
        # Build filter clauses
        must_clauses: list[dict[str, Any]] = [
            # Filter by entity_id
            {"term": {"entity_id": entity_id}},
            # Filter by time range
            {
                "range": {
                    "@timestamp": {
                        "gte": start.isoformat(),
                        "lte": end.isoformat(),
                    }
                }
            },
        ]

        # Add optional wildcard query on message field
        if query:
            must_clauses.append({
                "wildcard": {
                    "message": {
                        "value": query,
                        "case_insensitive": True,
                    }
                }
            })

        return {
            "query": {
                "bool": {
                    "must": must_clauses,
                }
            },
            "sort": [
                {"@timestamp": {"order": "asc"}}
            ],
            # Request 1 extra to detect has_more
            "size": self.MAX_RESULTS + 1,
            "_source": ["@timestamp", "message"],
        }

    def _parse_response(self, response_data: dict[str, Any]) -> LogQueryResult:
        """Parse Elasticsearch response into LogQueryResult.

        Args:
            response_data: Elasticsearch JSON response

        Returns:
            LogQueryResult with parsed logs and pagination info
        """
        hits = response_data.get("hits", {}).get("hits", [])

        # Check if we have more results than the limit
        has_more = len(hits) > self.MAX_RESULTS

        # Truncate to MAX_RESULTS if we got more
        if has_more:
            hits = hits[:self.MAX_RESULTS]

        # Parse log entries
        logs: list[LogEntry] = []
        for hit in hits:
            source = hit.get("_source", {})
            timestamp_str = source.get("@timestamp")
            message = source.get("message", "")

            if timestamp_str:
                # Parse ISO timestamp from Elasticsearch
                try:
                    # Handle both with and without timezone
                    if timestamp_str.endswith("Z"):
                        timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                    else:
                        timestamp = datetime.fromisoformat(timestamp_str)

                    logs.append(LogEntry(timestamp=timestamp, message=message))
                except ValueError as e:
                    logger.warning("Failed to parse timestamp %s: %s", timestamp_str, e)
                    continue

        # Compute window_start and window_end from actual results
        window_start: datetime | None = None
        window_end: datetime | None = None

        if logs:
            window_start = logs[0].timestamp
            # Add 1ms to window_end so polling with it as start excludes the last message
            window_end = logs[-1].timestamp + timedelta(milliseconds=1)

        return LogQueryResult(
            logs=logs,
            has_more=has_more,
            window_start=window_start,
            window_end=window_end,
        )
