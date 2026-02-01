"""Tests for ElasticsearchService."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import httpx
import pytest
from flask import Flask

from app.exceptions import ExternalServiceException, ServiceUnavailableException
from app.services.container import ServiceContainer


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
