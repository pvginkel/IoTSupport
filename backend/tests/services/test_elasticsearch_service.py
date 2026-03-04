"""Tests for ElasticsearchService."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import httpx
import pytest
from flask import Flask

from app.exceptions import ExternalServiceException, ServiceUnavailableException
from app.services.container import ServiceContainer
from app.services.elasticsearch_service import ElasticsearchService


class TestElasticsearchServiceQueryLogs:
    """Tests for query_logs method."""

    def test_query_logs_success(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test successful log query."""
        with app.app_context():
            es_service = container.elasticsearch_service()
            es_service.enabled = True

            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = {
                "hits": {
                    "hits": [
                        {
                            "_source": {
                                "@timestamp": "2026-02-01T14:00:00Z",
                                "message": "Log message 1",
                            }
                        },
                        {
                            "_source": {
                                "@timestamp": "2026-02-01T14:01:00Z",
                                "message": "Log message 2",
                            }
                        },
                    ]
                }
            }

            with patch.object(
                es_service._http_client,
                "post",
                return_value=mock_response
            ):
                result = es_service.query_logs(
                    entity_id="sensor.living_room",
                    start=datetime(2026, 2, 1, 14, 0, 0, tzinfo=UTC),
                    end=datetime(2026, 2, 1, 15, 0, 0, tzinfo=UTC),
                )

                assert len(result.logs) == 2
                assert result.logs[0].message == "Log message 1"
                assert result.logs[1].message == "Log message 2"
                assert result.has_more is False
                assert result.window_start is not None
                assert result.window_end is not None

    def test_query_logs_with_wildcard_query(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test log query with wildcard search."""
        with app.app_context():
            es_service = container.elasticsearch_service()
            es_service.enabled = True

            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = {
                "hits": {
                    "hits": [
                        {
                            "_source": {
                                "@timestamp": "2026-02-01T14:00:00Z",
                                "message": "Error: connection failed",
                            }
                        },
                    ]
                }
            }

            with patch.object(
                es_service._http_client,
                "post",
                return_value=mock_response
            ) as mock_post:
                result = es_service.query_logs(
                    entity_id="sensor.living_room",
                    start=datetime(2026, 2, 1, 14, 0, 0, tzinfo=UTC),
                    end=datetime(2026, 2, 1, 15, 0, 0, tzinfo=UTC),
                    query="error*",
                )

                assert len(result.logs) == 1

                # Verify wildcard was included in query
                call_args = mock_post.call_args
                query_body = call_args[1]["json"]
                must_clauses = query_body["query"]["bool"]["must"]
                wildcard_clause = [c for c in must_clauses if "wildcard" in c]
                assert len(wildcard_clause) == 1
                assert wildcard_clause[0]["wildcard"]["message"]["value"] == "error*"

    def test_query_logs_has_more_when_exceeds_limit(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test has_more is True when results exceed MAX_RESULTS."""
        with app.app_context():
            es_service = container.elasticsearch_service()
            es_service.enabled = True

            # Generate 1001 hits (one more than MAX_RESULTS)
            # Use proper timestamp format: YYYY-MM-DDTHH:MM:SS.sssZ
            hits = [
                {
                    "_source": {
                        "@timestamp": f"2026-02-01T14:00:00.{i:03d}Z",
                        "message": f"Log message {i}",
                    }
                }
                for i in range(1001)
            ]

            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = {"hits": {"hits": hits}}

            with patch.object(
                es_service._http_client,
                "post",
                return_value=mock_response
            ):
                result = es_service.query_logs(
                    entity_id="sensor.living_room",
                    start=datetime(2026, 2, 1, 14, 0, 0, tzinfo=UTC),
                    end=datetime(2026, 2, 1, 15, 0, 0, tzinfo=UTC),
                )

                assert result.has_more is True
                assert len(result.logs) == 1000  # Truncated to MAX_RESULTS

    def test_query_logs_empty_entity_id_returns_empty(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test that None entity_id returns empty result without hitting ES."""
        with app.app_context():
            es_service = container.elasticsearch_service()
            es_service.enabled = True

            with patch.object(
                es_service._http_client,
                "post"
            ) as mock_post:
                result = es_service.query_logs(
                    entity_id=None,
                    start=datetime(2026, 2, 1, 14, 0, 0, tzinfo=UTC),
                    end=datetime(2026, 2, 1, 15, 0, 0, tzinfo=UTC),
                )

                # Should not call Elasticsearch
                mock_post.assert_not_called()

                assert result.logs == []
                assert result.has_more is False
                assert result.window_start is None
                assert result.window_end is None

    def test_query_logs_connection_error_raises_service_unavailable(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test that connection errors raise ServiceUnavailableException."""
        with app.app_context():
            es_service = container.elasticsearch_service()
            es_service.enabled = True

            with patch.object(
                es_service._http_client,
                "post",
                side_effect=httpx.ConnectError("Connection refused")
            ):
                with pytest.raises(ServiceUnavailableException) as exc_info:
                    es_service.query_logs(
                        entity_id="sensor.living_room",
                        start=datetime(2026, 2, 1, 14, 0, 0, tzinfo=UTC),
                        end=datetime(2026, 2, 1, 15, 0, 0, tzinfo=UTC),
                    )

                assert "Connection failed" in str(exc_info.value)

    def test_query_logs_timeout_raises_service_unavailable(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test that timeout errors raise ServiceUnavailableException."""
        with app.app_context():
            es_service = container.elasticsearch_service()
            es_service.enabled = True

            with patch.object(
                es_service._http_client,
                "post",
                side_effect=httpx.TimeoutException("Request timed out")
            ):
                with pytest.raises(ServiceUnavailableException) as exc_info:
                    es_service.query_logs(
                        entity_id="sensor.living_room",
                        start=datetime(2026, 2, 1, 14, 0, 0, tzinfo=UTC),
                        end=datetime(2026, 2, 1, 15, 0, 0, tzinfo=UTC),
                    )

                assert "timed out" in str(exc_info.value)

    def test_query_logs_http_error_raises_external_service_exception(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test that HTTP errors raise ExternalServiceException."""
        with app.app_context():
            es_service = container.elasticsearch_service()
            es_service.enabled = True

            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_response.text = "Internal Server Error"

            with patch.object(
                es_service._http_client,
                "post",
                side_effect=httpx.HTTPStatusError(
                    "Server Error",
                    request=MagicMock(),
                    response=mock_response
                )
            ):
                with pytest.raises(ExternalServiceException) as exc_info:
                    es_service.query_logs(
                        entity_id="sensor.living_room",
                        start=datetime(2026, 2, 1, 14, 0, 0, tzinfo=UTC),
                        end=datetime(2026, 2, 1, 15, 0, 0, tzinfo=UTC),
                    )

                assert "HTTP 500" in str(exc_info.value)

    def test_query_logs_disabled_raises_service_unavailable(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test that disabled service raises ServiceUnavailableException."""
        with app.app_context():
            es_service = container.elasticsearch_service()
            es_service.enabled = False

            with pytest.raises(ServiceUnavailableException) as exc_info:
                es_service.query_logs(
                    entity_id="sensor.living_room",
                    start=datetime(2026, 2, 1, 14, 0, 0, tzinfo=UTC),
                    end=datetime(2026, 2, 1, 15, 0, 0, tzinfo=UTC),
                )

            assert "not configured" in str(exc_info.value)

    def test_query_logs_empty_results(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test handling of empty results."""
        with app.app_context():
            es_service = container.elasticsearch_service()
            es_service.enabled = True

            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = {"hits": {"hits": []}}

            with patch.object(
                es_service._http_client,
                "post",
                return_value=mock_response
            ):
                result = es_service.query_logs(
                    entity_id="sensor.living_room",
                    start=datetime(2026, 2, 1, 14, 0, 0, tzinfo=UTC),
                    end=datetime(2026, 2, 1, 15, 0, 0, tzinfo=UTC),
                )

                assert result.logs == []
                assert result.has_more is False
                assert result.window_start is None
                assert result.window_end is None


class TestElasticsearchServiceBuildQuery:
    """Tests for _build_query method."""

    def test_build_query_basic(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test basic query structure."""
        with app.app_context():
            es_service = container.elasticsearch_service()

            query = es_service._build_query(
                entity_id="sensor.test",
                start=datetime(2026, 2, 1, 14, 0, 0, tzinfo=UTC),
                end=datetime(2026, 2, 1, 15, 0, 0, tzinfo=UTC),
                query=None,
            )

            # Verify query structure
            assert "query" in query
            assert "bool" in query["query"]
            assert "must" in query["query"]["bool"]

            # Verify sort order (ascending)
            assert query["sort"][0]["@timestamp"]["order"] == "asc"

            # Verify size (MAX_RESULTS + 1 for pagination detection)
            assert query["size"] == 1001

            # Verify source fields
            assert "@timestamp" in query["_source"]
            assert "message" in query["_source"]

    def test_build_query_with_wildcard(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test query includes wildcard when provided."""
        with app.app_context():
            es_service = container.elasticsearch_service()

            query = es_service._build_query(
                entity_id="sensor.test",
                start=datetime(2026, 2, 1, 14, 0, 0, tzinfo=UTC),
                end=datetime(2026, 2, 1, 15, 0, 0, tzinfo=UTC),
                query="error*",
            )

            must_clauses = query["query"]["bool"]["must"]

            # Find wildcard clause
            wildcard_clauses = [c for c in must_clauses if "wildcard" in c]
            assert len(wildcard_clauses) == 1
            assert wildcard_clauses[0]["wildcard"]["message"]["value"] == "error*"
            assert wildcard_clauses[0]["wildcard"]["message"]["case_insensitive"] is True


class TestElasticsearchServiceAuth:
    """Tests for authentication handling."""

    def test_get_auth_with_credentials(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test auth returns credentials when configured."""
        with app.app_context():
            es_service = container.elasticsearch_service()
            es_service.config = MagicMock()
            es_service.config.elasticsearch_username = "testuser"
            es_service.config.elasticsearch_password = "testpass"

            auth = es_service._get_auth()

            assert auth == ("testuser", "testpass")

    def test_get_auth_without_credentials(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test auth returns None when not configured."""
        with app.app_context():
            es_service = container.elasticsearch_service()
            es_service.config = MagicMock()
            es_service.config.elasticsearch_username = None
            es_service.config.elasticsearch_password = None

            auth = es_service._get_auth()

            assert auth is None

    def test_get_auth_partial_credentials(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test auth returns None when only username is configured."""
        with app.app_context():
            es_service = container.elasticsearch_service()
            es_service.config = MagicMock()
            es_service.config.elasticsearch_username = "testuser"
            es_service.config.elasticsearch_password = None

            auth = es_service._get_auth()

            assert auth is None


class TestElasticsearchServiceParseResponse:
    """Tests for _parse_response method."""

    def test_parse_response_handles_timezone_z(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test parsing timestamps with Z suffix."""
        with app.app_context():
            es_service = container.elasticsearch_service()

            response_data = {
                "hits": {
                    "hits": [
                        {
                            "_source": {
                                "@timestamp": "2026-02-01T14:00:00Z",
                                "message": "Test message",
                            }
                        }
                    ]
                }
            }

            result = es_service._parse_response(response_data)

            assert len(result.logs) == 1
            assert result.logs[0].timestamp.tzinfo is not None

    def test_parse_response_handles_timezone_offset(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test parsing timestamps with timezone offset."""
        with app.app_context():
            es_service = container.elasticsearch_service()

            response_data = {
                "hits": {
                    "hits": [
                        {
                            "_source": {
                                "@timestamp": "2026-02-01T14:00:00+00:00",
                                "message": "Test message",
                            }
                        }
                    ]
                }
            }

            result = es_service._parse_response(response_data)

            assert len(result.logs) == 1

    def test_parse_response_skips_invalid_timestamp(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test that invalid timestamps are skipped."""
        with app.app_context():
            es_service = container.elasticsearch_service()

            response_data = {
                "hits": {
                    "hits": [
                        {
                            "_source": {
                                "@timestamp": "invalid-timestamp",
                                "message": "Should be skipped",
                            }
                        },
                        {
                            "_source": {
                                "@timestamp": "2026-02-01T14:00:00Z",
                                "message": "Valid entry",
                            }
                        }
                    ]
                }
            }

            result = es_service._parse_response(response_data)

            assert len(result.logs) == 1
            assert result.logs[0].message == "Valid entry"

    def test_parse_response_handles_missing_message(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test handling of missing message field."""
        with app.app_context():
            es_service = container.elasticsearch_service()

            response_data = {
                "hits": {
                    "hits": [
                        {
                            "_source": {
                                "@timestamp": "2026-02-01T14:00:00Z",
                                # No message field
                            }
                        }
                    ]
                }
            }

            result = es_service._parse_response(response_data)

            assert len(result.logs) == 1
            assert result.logs[0].message == ""  # Empty string default


class TestElasticsearchServiceBackwardMode:
    """Tests for backward scroll mode."""

    def test_build_query_backward_sort_desc(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Backward mode uses descending sort and omits gte when start is None."""
        with app.app_context():
            es_service = container.elasticsearch_service()

            query = es_service._build_query(
                entity_id="sensor.test",
                start=None,
                end=datetime(2026, 2, 1, 15, 0, 0, tzinfo=UTC),
                query=None,
                backward=True,
            )

            # Sort must be descending
            assert query["sort"][0]["@timestamp"]["order"] == "desc"

            # Time range must have lte but NOT gte
            must_clauses = query["query"]["bool"]["must"]
            range_clause = [c for c in must_clauses if "range" in c][0]
            ts_range = range_clause["range"]["@timestamp"]
            assert "lte" in ts_range
            assert "gte" not in ts_range

    def test_build_query_backward_with_start_includes_gte(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Backward mode with explicit start still includes gte."""
        with app.app_context():
            es_service = container.elasticsearch_service()

            query = es_service._build_query(
                entity_id="sensor.test",
                start=datetime(2026, 2, 1, 14, 0, 0, tzinfo=UTC),
                end=datetime(2026, 2, 1, 15, 0, 0, tzinfo=UTC),
                query=None,
                backward=True,
            )

            must_clauses = query["query"]["bool"]["must"]
            range_clause = [c for c in must_clauses if "range" in c][0]
            ts_range = range_clause["range"]["@timestamp"]
            assert "gte" in ts_range
            assert "lte" in ts_range

    def test_parse_response_backward_reverses_results(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Backward mode reverses results to chronological order and adjusts window."""
        with app.app_context():
            es_service = container.elasticsearch_service()

            # ES returns desc order: newest first
            response_data = {
                "hits": {
                    "hits": [
                        {
                            "_source": {
                                "@timestamp": "2026-02-01T14:02:00Z",
                                "message": "Third",
                            }
                        },
                        {
                            "_source": {
                                "@timestamp": "2026-02-01T14:01:00Z",
                                "message": "Second",
                            }
                        },
                        {
                            "_source": {
                                "@timestamp": "2026-02-01T14:00:00Z",
                                "message": "First",
                            }
                        },
                    ]
                }
            }

            result = es_service._parse_response(response_data, backward=True)

            # Results should be reversed to chronological (ascending) order
            assert result.logs[0].message == "First"
            assert result.logs[1].message == "Second"
            assert result.logs[2].message == "Third"

            # window_start should be first entry timestamp - 1ms (exclusive lower bound)
            assert result.window_start == (
                datetime(2026, 2, 1, 14, 0, 0, tzinfo=UTC)
                - timedelta(milliseconds=1)
            )
            # window_end should be last entry timestamp (no offset)
            assert result.window_end == datetime(2026, 2, 1, 14, 2, 0, tzinfo=UTC)

    def test_parse_response_forward_unchanged(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Forward mode (default) keeps existing window boundary behavior."""
        with app.app_context():
            es_service = container.elasticsearch_service()

            response_data = {
                "hits": {
                    "hits": [
                        {
                            "_source": {
                                "@timestamp": "2026-02-01T14:00:00Z",
                                "message": "First",
                            }
                        },
                        {
                            "_source": {
                                "@timestamp": "2026-02-01T14:02:00Z",
                                "message": "Last",
                            }
                        },
                    ]
                }
            }

            result = es_service._parse_response(response_data, backward=False)

            assert result.window_start == datetime(2026, 2, 1, 14, 0, 0, tzinfo=UTC)
            assert result.window_end == (
                datetime(2026, 2, 1, 14, 2, 0, tzinfo=UTC)
                + timedelta(milliseconds=1)
            )

    def test_query_logs_backward_mode(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Integration test: backward flag flows through query_logs to build and parse."""
        with app.app_context():
            es_service = container.elasticsearch_service()
            es_service.enabled = True

            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = {
                "hits": {
                    "hits": [
                        {
                            "_source": {
                                "@timestamp": "2026-02-01T14:01:00Z",
                                "message": "Newer",
                            }
                        },
                        {
                            "_source": {
                                "@timestamp": "2026-02-01T14:00:00Z",
                                "message": "Older",
                            }
                        },
                    ]
                }
            }

            with patch.object(
                es_service._http_client,
                "post",
                return_value=mock_response,
            ) as mock_post:
                result = es_service.query_logs(
                    entity_id="sensor.test",
                    start=None,
                    end=datetime(2026, 2, 1, 15, 0, 0, tzinfo=UTC),
                    backward=True,
                )

                # Verify descending sort was used
                call_args = mock_post.call_args
                query_body = call_args[1]["json"]
                assert query_body["sort"][0]["@timestamp"]["order"] == "desc"

                # Verify no gte in time range
                must_clauses = query_body["query"]["bool"]["must"]
                range_clause = [c for c in must_clauses if "range" in c][0]
                assert "gte" not in range_clause["range"]["@timestamp"]

            # Results should be reversed to chronological order
            assert result.logs[0].message == "Older"
            assert result.logs[1].message == "Newer"


class TestElasticsearchServiceSeedLogs:
    """Tests for in-memory seeded log functionality."""

    @pytest.fixture(autouse=True)
    def _clear_seeded(self, app: Flask, container: ServiceContainer) -> None:
        """Ensure seeded logs are cleared between tests."""
        with app.app_context():
            es = container.elasticsearch_service()
            es.clear_all_seeded_logs()

    def _get_service(self, app: Flask, container: ServiceContainer) -> ElasticsearchService:
        with app.app_context():
            return container.elasticsearch_service()

    def test_seed_logs_generates_entries(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """1500 entries stored, sorted ascending, messages match format."""
        with app.app_context():
            es = container.elasticsearch_service()
            start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
            end = datetime(2026, 1, 1, 1, 0, 0, tzinfo=UTC)

            count, ws, we = es.seed_logs("dev.a", 1500, start, end)

            assert count == 1500
            assert ws == start
            assert we == end

            entries = es._seeded_logs["dev.a"]
            assert len(entries) == 1500
            # Sorted ascending
            for i in range(len(entries) - 1):
                assert entries[i].timestamp <= entries[i + 1].timestamp
            # Message format
            assert entries[0].message == "Seeded log entry 1"
            assert entries[1499].message == "Seeded log entry 1500"

    def test_seed_logs_single_entry(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """count=1 produces a single entry at start_time."""
        with app.app_context():
            es = container.elasticsearch_service()
            start = datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC)
            end = datetime(2026, 3, 1, 13, 0, 0, tzinfo=UTC)

            es.seed_logs("dev.a", 1, start, end)

            entries = es._seeded_logs["dev.a"]
            assert len(entries) == 1
            assert entries[0].timestamp == start
            assert entries[0].message == "Seeded log entry 1"

    def test_seed_logs_two_entries(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """count=2 produces one at start_time and one at end_time."""
        with app.app_context():
            es = container.elasticsearch_service()
            start = datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC)
            end = datetime(2026, 3, 1, 13, 0, 0, tzinfo=UTC)

            es.seed_logs("dev.a", 2, start, end)

            entries = es._seeded_logs["dev.a"]
            assert len(entries) == 2
            assert entries[0].timestamp == start
            assert entries[1].timestamp == end

    def test_seed_logs_replaces_previous(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Re-seeding same entity_id replaces old data."""
        with app.app_context():
            es = container.elasticsearch_service()
            start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
            end = datetime(2026, 1, 1, 1, 0, 0, tzinfo=UTC)

            es.seed_logs("dev.a", 10, start, end)
            assert len(es._seeded_logs["dev.a"]) == 10

            es.seed_logs("dev.a", 5, start, end)
            assert len(es._seeded_logs["dev.a"]) == 5

    def test_clear_seeded_logs(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Removes one entity_id."""
        with app.app_context():
            es = container.elasticsearch_service()
            start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
            end = datetime(2026, 1, 1, 1, 0, 0, tzinfo=UTC)

            es.seed_logs("dev.a", 5, start, end)
            es.seed_logs("dev.b", 5, start, end)

            es.clear_seeded_logs("dev.a")
            assert "dev.a" not in es._seeded_logs
            assert "dev.b" in es._seeded_logs

    def test_clear_all_seeded_logs(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Clears everything."""
        with app.app_context():
            es = container.elasticsearch_service()
            start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
            end = datetime(2026, 1, 1, 1, 0, 0, tzinfo=UTC)

            es.seed_logs("dev.a", 5, start, end)
            es.seed_logs("dev.b", 5, start, end)

            es.clear_all_seeded_logs()
            assert len(es._seeded_logs) == 0

    def test_query_seeded_forward(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """1500 seeded, forward query returns 1000, has_more=True, correct window."""
        with app.app_context():
            es = container.elasticsearch_service()
            start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
            end = datetime(2026, 1, 1, 1, 0, 0, tzinfo=UTC)
            es.seed_logs("dev.a", 1500, start, end)

            result = es.query_logs(
                entity_id="dev.a",
                start=start,
                end=end,
            )

            assert len(result.logs) == 1000
            assert result.has_more is True
            assert result.window_start == start
            assert result.window_end == result.logs[-1].timestamp + timedelta(milliseconds=1)
            # Chronological order
            for i in range(len(result.logs) - 1):
                assert result.logs[i].timestamp <= result.logs[i + 1].timestamp

    def test_query_seeded_all_fit(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """500 seeded, returns all, has_more=False."""
        with app.app_context():
            es = container.elasticsearch_service()
            start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
            end = datetime(2026, 1, 1, 1, 0, 0, tzinfo=UTC)
            es.seed_logs("dev.a", 500, start, end)

            result = es.query_logs(
                entity_id="dev.a",
                start=start,
                end=end,
            )

            assert len(result.logs) == 500
            assert result.has_more is False

    def test_query_seeded_backward(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Backward mode: results chronological, window_start has -1ms offset."""
        with app.app_context():
            es = container.elasticsearch_service()
            start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
            end = datetime(2026, 1, 1, 1, 0, 0, tzinfo=UTC)
            es.seed_logs("dev.a", 500, start, end)

            result = es.query_logs(
                entity_id="dev.a",
                start=None,
                end=end,
                backward=True,
            )

            assert len(result.logs) == 500
            assert result.has_more is False
            # Chronological order
            for i in range(len(result.logs) - 1):
                assert result.logs[i].timestamp <= result.logs[i + 1].timestamp
            # Window boundaries for backward mode
            assert result.window_start == result.logs[0].timestamp - timedelta(milliseconds=1)
            assert result.window_end == result.logs[-1].timestamp

    def test_query_seeded_time_range_filter(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Only entries within [start, end] returned."""
        with app.app_context():
            es = container.elasticsearch_service()
            start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
            end = datetime(2026, 1, 1, 1, 0, 0, tzinfo=UTC)
            es.seed_logs("dev.a", 100, start, end)

            # Query a narrow window in the middle
            q_start = datetime(2026, 1, 1, 0, 20, 0, tzinfo=UTC)
            q_end = datetime(2026, 1, 1, 0, 40, 0, tzinfo=UTC)

            result = es.query_logs(
                entity_id="dev.a",
                start=q_start,
                end=q_end,
            )

            # All returned entries must be within the queried range
            for entry in result.logs:
                assert entry.timestamp >= q_start
                assert entry.timestamp <= q_end
            # Should have fewer than total
            assert len(result.logs) < 100

    def test_query_seeded_wildcard_filter(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Query '*entry 5*' filters correctly."""
        with app.app_context():
            es = container.elasticsearch_service()
            start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
            end = datetime(2026, 1, 1, 1, 0, 0, tzinfo=UTC)
            es.seed_logs("dev.a", 100, start, end)

            result = es.query_logs(
                entity_id="dev.a",
                start=start,
                end=end,
                query="*entry 5*",
            )

            # Should match entries 5, 50, 51-59 = 12 entries
            assert len(result.logs) > 0
            for entry in result.logs:
                assert "entry 5" in entry.message.lower()

    def test_query_seeded_empty_match(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """No matches returns empty result with None windows."""
        with app.app_context():
            es = container.elasticsearch_service()
            start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
            end = datetime(2026, 1, 1, 1, 0, 0, tzinfo=UTC)
            es.seed_logs("dev.a", 10, start, end)

            result = es.query_logs(
                entity_id="dev.a",
                start=start,
                end=end,
                query="*nomatch*",
            )

            assert len(result.logs) == 0
            assert result.has_more is False
            assert result.window_start is None
            assert result.window_end is None

    def test_query_seeded_skips_es_disabled(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Seeded path works even when enabled=False."""
        with app.app_context():
            es = container.elasticsearch_service()
            es.enabled = False
            start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
            end = datetime(2026, 1, 1, 1, 0, 0, tzinfo=UTC)
            es.seed_logs("dev.a", 10, start, end)

            result = es.query_logs(
                entity_id="dev.a",
                start=start,
                end=end,
            )

            assert len(result.logs) == 10

    def test_query_unseeded_entity_falls_through(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """entity_id not in seeded dict follows normal ES path."""
        with app.app_context():
            es = container.elasticsearch_service()
            es.enabled = True
            start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
            end = datetime(2026, 1, 1, 1, 0, 0, tzinfo=UTC)

            # Seed a different entity
            es.seed_logs("dev.a", 10, start, end)

            # Query for unseeded entity - should hit ES (mock it)
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = {"hits": {"hits": []}}

            with patch.object(
                es._http_client, "post", return_value=mock_response
            ) as mock_post:
                result = es.query_logs(
                    entity_id="dev.other",
                    start=start,
                    end=end,
                )

                # Should have called ES
                mock_post.assert_called_once()
                assert result.logs == []
