"""Elasticsearch service for querying device logs."""

import fnmatch
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

import httpx
from prometheus_client import Counter, Histogram

from app.exceptions import ExternalServiceException, ServiceUnavailableException

if TYPE_CHECKING:
    from app.app_config import AppSettings

logger = logging.getLogger(__name__)

# Elasticsearch Prometheus metrics (module-level)
ES_OPERATIONS_TOTAL = Counter(
    "iot_elasticsearch_operations_total",
    "Total Elasticsearch operations",
    ["operation", "status"],
)
ES_QUERY_DURATION = Histogram(
    "iot_elasticsearch_query_duration_seconds",
    "Duration of Elasticsearch queries in seconds",
    ["operation"],
)


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
        config: "AppSettings",
    ) -> None:
        """Initialize Elasticsearch service.

        Args:
            config: Application settings containing Elasticsearch configuration
        """
        self.config = config

        # HTTP client for API calls with connection pooling
        self._http_client = httpx.Client(timeout=10.0)

        # Check if Elasticsearch is configured
        self.enabled = bool(config.elasticsearch_url)

        # In-memory seeded logs for testing (entity_id -> sorted list of LogEntry)
        self._seeded_logs: dict[str, list[LogEntry]] = {}

        if self.enabled:
            logger.info(
                "ElasticsearchService initialized with URL: %s",
                config.elasticsearch_url
            )
        else:
            logger.warning("ElasticsearchService disabled - ELASTICSEARCH_URL not configured")

    # ------------------------------------------------------------------
    # Seeded log management (testing only)
    # ------------------------------------------------------------------

    def seed_logs(
        self,
        entity_id: str,
        count: int,
        start_time: datetime,
        end_time: datetime,
    ) -> tuple[int, datetime, datetime]:
        """Generate deterministic log entries in memory for testing.

        Args:
            entity_id: Device entity ID to seed logs for
            count: Number of entries to generate (>= 1)
            start_time: Timestamp of the first entry
            end_time: Timestamp of the last entry

        Returns:
            Tuple of (count, start_time, end_time)
        """
        if count == 1:
            interval = timedelta(0)
        else:
            interval = (end_time - start_time) / (count - 1)

        entries = [
            LogEntry(
                timestamp=start_time + interval * i,
                message=f"Seeded log entry {i + 1}",
            )
            for i in range(count)
        ]

        # Ensure the last entry is exactly at end_time (avoids float rounding drift)
        if count > 1:
            entries[-1] = LogEntry(timestamp=end_time, message=entries[-1].message)

        self._seeded_logs[entity_id] = entries
        logger.info("Seeded %d log entries for entity_id=%s", count, entity_id)
        return (count, start_time, end_time)

    def clear_seeded_logs(self, entity_id: str) -> None:
        """Remove seeded logs for a single entity_id."""
        self._seeded_logs.pop(entity_id, None)

    def clear_all_seeded_logs(self) -> None:
        """Remove all seeded logs."""
        self._seeded_logs.clear()

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
        try:
            ES_OPERATIONS_TOTAL.labels(operation=operation, status=status).inc()
        except Exception as e:
            logger.error("Error recording ES operation metric: %s", e)

    def _record_duration(self, operation: str, duration: float) -> None:
        """Record Elasticsearch query duration."""
        try:
            ES_QUERY_DURATION.labels(operation=operation).observe(duration)
        except Exception as e:
            logger.error("Error recording ES query metric: %s", e)

    def query_logs(
        self,
        entity_id: str | None,
        start: datetime | None,
        end: datetime,
        query: str | None = None,
        backward: bool = False,
    ) -> LogQueryResult:
        """Query device logs from Elasticsearch.

        Args:
            entity_id: Device entity ID to filter by. If None, returns empty result.
            start: Start of time range (inclusive). None in backward mode (no lower bound).
            end: End of time range (inclusive)
            query: Optional wildcard query to filter messages
            backward: If True, query in descending order and reverse results to
                chronological order. Used for backward scroll (only `end` provided).

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

        # Serve from in-memory seeded data when available (testing path)
        if entity_id in self._seeded_logs:
            return self._query_seeded_logs(entity_id, start, end, query, backward)

        if not self.enabled:
            raise ServiceUnavailableException(
                "Elasticsearch",
                "Elasticsearch URL not configured"
            )

        start_time = time.perf_counter()
        status = "success"

        try:
            result = self._execute_query(entity_id, start, end, query, backward)

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
        start: datetime | None,
        end: datetime,
        query: str | None,
        backward: bool = False,
    ) -> LogQueryResult:
        """Execute the Elasticsearch query.

        Args:
            entity_id: Device entity ID to filter by
            start: Start of time range (None omits the lower bound)
            end: End of time range
            query: Optional wildcard query for message field
            backward: If True, sort descending and reverse results

        Returns:
            LogQueryResult with query results
        """
        # Build the Elasticsearch query
        # Request 1 extra to detect if more results exist
        es_query = self._build_query(entity_id, start, end, query, backward)

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
        return self._parse_response(response.json(), backward)

    def _build_query(
        self,
        entity_id: str,
        start: datetime | None,
        end: datetime,
        query: str | None,
        backward: bool = False,
    ) -> dict[str, Any]:
        """Build the Elasticsearch query.

        Args:
            entity_id: Device entity ID to filter by
            start: Start of time range (None omits the lower bound)
            end: End of time range
            query: Optional wildcard query for message field
            backward: If True, sort descending (caller reverses results)

        Returns:
            Elasticsearch query dict
        """
        # Build time range filter — omit gte when start is None (backward scroll)
        time_range: dict[str, str] = {"lte": end.isoformat()}
        if start is not None:
            time_range["gte"] = start.isoformat()

        # Build filter clauses
        must_clauses: list[dict[str, Any]] = [
            {"term": {"entity_id": entity_id}},
            {"range": {"@timestamp": time_range}},
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

        sort_order = "desc" if backward else "asc"

        return {
            "query": {
                "bool": {
                    "must": must_clauses,
                }
            },
            "sort": [
                {"@timestamp": {"order": sort_order}}
            ],
            # Request 1 extra to detect has_more
            "size": self.MAX_RESULTS + 1,
            "_source": ["@timestamp", "message"],
        }

    def _parse_response(
        self,
        response_data: dict[str, Any],
        backward: bool = False,
    ) -> LogQueryResult:
        """Parse Elasticsearch response into LogQueryResult.

        Args:
            response_data: Elasticsearch JSON response
            backward: If True, results arrived in descending order and need
                reversing. Window boundaries are also adjusted for backward
                pagination.

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

        # In backward mode, ES returned desc order — reverse to chronological
        if backward:
            logs.reverse()

        # Compute window_start and window_end from actual results
        window_start: datetime | None = None
        window_end: datetime | None = None

        if logs:
            if backward:
                # Backward scroll: window_start is the exclusive lower bound for the
                # next backward request (subtract 1ms so the caller can pass it as `end`
                # without re-fetching the oldest entry).
                window_start = logs[0].timestamp - timedelta(milliseconds=1)
                window_end = logs[-1].timestamp
            else:
                window_start = logs[0].timestamp
                # Add 1ms to window_end so polling with it as start excludes the last message
                window_end = logs[-1].timestamp + timedelta(milliseconds=1)

        return LogQueryResult(
            logs=logs,
            has_more=has_more,
            window_start=window_start,
            window_end=window_end,
        )

    # ------------------------------------------------------------------
    # Seeded log query (in-memory, mirrors ES query semantics)
    # ------------------------------------------------------------------

    def _query_seeded_logs(
        self,
        entity_id: str,
        start: datetime | None,
        end: datetime,
        query: str | None,
        backward: bool,
    ) -> LogQueryResult:
        """Query from in-memory seeded logs, mirroring ES query semantics."""
        entries = self._seeded_logs[entity_id]  # already sorted ascending

        # Filter by time range
        filtered = [e for e in entries if e.timestamp <= end]
        if start is not None:
            filtered = [e for e in filtered if e.timestamp >= start]

        # Filter by wildcard query (case-insensitive, fnmatch matches ES wildcards)
        if query:
            filtered = [
                e for e in filtered
                if fnmatch.fnmatch(e.message.lower(), query.lower())
            ]

        # Empty result short-circuit
        if not filtered:
            return LogQueryResult(
                logs=[], has_more=False, window_start=None, window_end=None,
            )

        # Pagination and ordering
        if backward:
            # Reverse to desc, truncate, detect has_more, then reverse back
            filtered.reverse()
            has_more = len(filtered) > self.MAX_RESULTS
            if has_more:
                filtered = filtered[:self.MAX_RESULTS]
            filtered.reverse()
        else:
            has_more = len(filtered) > self.MAX_RESULTS
            if has_more:
                filtered = filtered[:self.MAX_RESULTS]

        # Window boundaries (same logic as _parse_response)
        if backward:
            window_start = filtered[0].timestamp - timedelta(milliseconds=1)
            window_end = filtered[-1].timestamp
        else:
            window_start = filtered[0].timestamp
            window_end = filtered[-1].timestamp + timedelta(milliseconds=1)

        return LogQueryResult(
            logs=filtered,
            has_more=has_more,
            window_start=window_start,
            window_end=window_end,
        )
