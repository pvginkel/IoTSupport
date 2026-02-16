"""Tests for device SSE testing API endpoints.

Covers the three testing-only endpoints:
- POST /api/testing/devices/logs/inject
- GET  /api/testing/devices/logs/subscriptions
- POST /api/testing/rotation/nudge
"""

from collections.abc import Generator
from typing import Any
from unittest.mock import patch

import pytest
from flask.testing import FlaskClient

from app.services.container import ServiceContainer
from app.services.device_log_stream_service import DeviceLogStreamService
from app.services.rotation_nudge_service import RotationNudgeService

# Re-use the testing fixtures defined in test_testing.py. Importing the
# module makes pytest discover the fixtures via conftest mechanics. We
# import the fixture functions directly so that pytest registers them in
# this module's scope without requiring conftest changes.
from tests.api.test_testing import (  # noqa: I001
    testing_app,  # noqa: F401
    testing_app_settings,  # noqa: F401
    testing_client,  # noqa: F401
    testing_container,  # noqa: F401
    testing_settings,  # noqa: F401
    testing_template_connection,  # noqa: F401
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def device_log_stream_service(
    testing_container: ServiceContainer,  # noqa: F811
) -> DeviceLogStreamService:
    """Access the DeviceLogStreamService singleton from the testing container."""
    return testing_container.device_log_stream_service()


@pytest.fixture
def rotation_nudge_service(
    testing_container: ServiceContainer,  # noqa: F811
) -> RotationNudgeService:
    """Access the RotationNudgeService singleton from the testing container."""
    return testing_container.rotation_nudge_service()


@pytest.fixture
def populate_subscriptions(
    device_log_stream_service: DeviceLogStreamService,
) -> Generator[None]:
    """Populate the in-memory subscription maps with test data, then clean up."""
    svc = device_log_stream_service

    # Directly populate internal maps (avoids needing real SSE connections)
    with svc._lock:
        svc._subscriptions_by_entity_id["device_a"] = {"req-1", "req-2"}
        svc._subscriptions_by_entity_id["device_b"] = {"req-3"}
        svc._subscriptions_by_request_id["req-1"] = {"device_a"}
        svc._subscriptions_by_request_id["req-2"] = {"device_a"}
        svc._subscriptions_by_request_id["req-3"] = {"device_b"}

    yield

    # Clean up
    with svc._lock:
        svc._subscriptions_by_entity_id.clear()
        svc._subscriptions_by_request_id.clear()


# ===========================================================================
# Testing guard (non-testing mode)
# ===========================================================================


class TestDeviceSSEEndpointsDisabled:
    """Verify all three endpoints return 400 when not in testing mode."""

    def test_inject_returns_400_when_not_testing(self, client: FlaskClient) -> None:
        response = client.post(
            "/api/testing/devices/logs/inject",
            json={
                "device_entity_id": "sensor.test",
                "logs": [{"message": "hello"}],
            },
        )
        assert response.status_code == 400
        data = response.get_json()
        assert data["code"] == "ROUTE_NOT_AVAILABLE"
        assert "FLASK_ENV=testing" in data["details"]["message"]

    def test_subscriptions_returns_400_when_not_testing(self, client: FlaskClient) -> None:
        response = client.get("/api/testing/devices/logs/subscriptions")
        assert response.status_code == 400
        data = response.get_json()
        assert data["code"] == "ROUTE_NOT_AVAILABLE"

    def test_nudge_returns_400_when_not_testing(self, client: FlaskClient) -> None:
        response = client.post("/api/testing/rotation/nudge")
        assert response.status_code == 400
        data = response.get_json()
        assert data["code"] == "ROUTE_NOT_AVAILABLE"


# ===========================================================================
# POST /api/testing/devices/logs/inject
# ===========================================================================


class TestInjectDeviceLogs:
    """Tests for the log injection endpoint."""

    def test_inject_success(
        self,
        testing_client: FlaskClient,  # noqa: F811
        device_log_stream_service: DeviceLogStreamService,
    ) -> None:
        """Valid payload returns 200 with forwarded count."""
        with patch.object(
            device_log_stream_service, "forward_logs"
        ) as mock_forward:
            response = testing_client.post(
                "/api/testing/devices/logs/inject",
                json={
                    "device_entity_id": "sensor.test_abc",
                    "logs": [
                        {"message": "Temperature: 22.5C"},
                        {"message": "Humidity: 45%"},
                    ],
                },
            )

        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "accepted"
        assert data["forwarded"] == 2

        # Verify forward_logs was called with enriched documents
        mock_forward.assert_called_once()
        documents = mock_forward.call_args[0][0]
        assert len(documents) == 2

        for doc in documents:
            assert doc["entity_id"] == "sensor.test_abc"
            assert "@timestamp" in doc
            assert "message" in doc

        assert documents[0]["message"] == "Temperature: 22.5C"
        assert documents[1]["message"] == "Humidity: 45%"

    def test_inject_single_log(
        self,
        testing_client: FlaskClient,  # noqa: F811
        device_log_stream_service: DeviceLogStreamService,
    ) -> None:
        """A single log entry is valid."""
        with patch.object(
            device_log_stream_service, "forward_logs"
        ) as mock_forward:
            response = testing_client.post(
                "/api/testing/devices/logs/inject",
                json={
                    "device_entity_id": "relay.garage",
                    "logs": [{"message": "Relay toggled"}],
                },
            )

        assert response.status_code == 200
        data = response.get_json()
        assert data["forwarded"] == 1
        mock_forward.assert_called_once()

    def test_inject_preserves_extra_fields(
        self,
        testing_client: FlaskClient,  # noqa: F811
        device_log_stream_service: DeviceLogStreamService,
    ) -> None:
        """Extra fields in log entries are preserved in forwarded documents."""
        with patch.object(
            device_log_stream_service, "forward_logs"
        ) as mock_forward:
            response = testing_client.post(
                "/api/testing/devices/logs/inject",
                json={
                    "device_entity_id": "sensor.test",
                    "logs": [
                        {"message": "Reading", "level": "INFO", "temperature": 22.5},
                    ],
                },
            )

        assert response.status_code == 200
        documents = mock_forward.call_args[0][0]
        assert documents[0]["level"] == "INFO"
        assert documents[0]["temperature"] == 22.5

    def test_inject_missing_device_entity_id(
        self,
        testing_client: FlaskClient,  # noqa: F811
    ) -> None:
        """Missing device_entity_id returns 400."""
        response = testing_client.post(
            "/api/testing/devices/logs/inject",
            json={
                "logs": [{"message": "hello"}],
            },
        )
        assert response.status_code == 400

    def test_inject_empty_device_entity_id(
        self,
        testing_client: FlaskClient,  # noqa: F811
    ) -> None:
        """Empty string device_entity_id returns 400."""
        response = testing_client.post(
            "/api/testing/devices/logs/inject",
            json={
                "device_entity_id": "",
                "logs": [{"message": "hello"}],
            },
        )
        assert response.status_code == 400

    def test_inject_empty_logs_array(
        self,
        testing_client: FlaskClient,  # noqa: F811
    ) -> None:
        """Empty logs array returns 400."""
        response = testing_client.post(
            "/api/testing/devices/logs/inject",
            json={
                "device_entity_id": "sensor.test",
                "logs": [],
            },
        )
        assert response.status_code == 400

    def test_inject_missing_logs_field(
        self,
        testing_client: FlaskClient,  # noqa: F811
    ) -> None:
        """Missing logs field returns 400."""
        response = testing_client.post(
            "/api/testing/devices/logs/inject",
            json={
                "device_entity_id": "sensor.test",
            },
        )
        assert response.status_code == 400

    def test_inject_log_entry_missing_message(
        self,
        testing_client: FlaskClient,  # noqa: F811
    ) -> None:
        """Log entry without message field returns 400."""
        response = testing_client.post(
            "/api/testing/devices/logs/inject",
            json={
                "device_entity_id": "sensor.test",
                "logs": [{"level": "INFO"}],
            },
        )
        assert response.status_code == 400

    def test_inject_log_entry_empty_message(
        self,
        testing_client: FlaskClient,  # noqa: F811
    ) -> None:
        """Log entry with empty message returns 400."""
        response = testing_client.post(
            "/api/testing/devices/logs/inject",
            json={
                "device_entity_id": "sensor.test",
                "logs": [{"message": ""}],
            },
        )
        assert response.status_code == 400

    def test_inject_missing_body(
        self,
        testing_client: FlaskClient,  # noqa: F811
    ) -> None:
        """No request body returns 400."""
        response = testing_client.post(
            "/api/testing/devices/logs/inject",
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_inject_timestamp_is_iso_format(
        self,
        testing_client: FlaskClient,  # noqa: F811
        device_log_stream_service: DeviceLogStreamService,
    ) -> None:
        """The @timestamp field is a valid ISO 8601 string."""
        from datetime import datetime

        with patch.object(
            device_log_stream_service, "forward_logs"
        ) as mock_forward:
            testing_client.post(
                "/api/testing/devices/logs/inject",
                json={
                    "device_entity_id": "sensor.test",
                    "logs": [{"message": "check timestamp"}],
                },
            )

        documents = mock_forward.call_args[0][0]
        ts = documents[0]["@timestamp"]
        # Should parse without error
        parsed = datetime.fromisoformat(ts)
        assert parsed is not None


# ===========================================================================
# GET /api/testing/devices/logs/subscriptions
# ===========================================================================


class TestGetLogSubscriptions:
    """Tests for the subscription status endpoint."""

    def test_no_subscriptions_returns_empty(
        self,
        testing_client: FlaskClient,  # noqa: F811
    ) -> None:
        """Returns empty subscriptions list when none exist."""
        response = testing_client.get("/api/testing/devices/logs/subscriptions")

        assert response.status_code == 200
        data = response.get_json()
        assert data["subscriptions"] == []

    @pytest.mark.usefixtures("populate_subscriptions")
    def test_all_subscriptions(
        self,
        testing_client: FlaskClient,  # noqa: F811
    ) -> None:
        """Returns all subscriptions when no filter is applied."""
        response = testing_client.get("/api/testing/devices/logs/subscriptions")

        assert response.status_code == 200
        data = response.get_json()
        subs = data["subscriptions"]
        assert len(subs) == 2

        # Build a lookup for easy assertion
        by_entity: dict[str, Any] = {s["device_entity_id"]: s for s in subs}

        assert "device_a" in by_entity
        assert sorted(by_entity["device_a"]["request_ids"]) == ["req-1", "req-2"]

        assert "device_b" in by_entity
        assert by_entity["device_b"]["request_ids"] == ["req-3"]

    @pytest.mark.usefixtures("populate_subscriptions")
    def test_filter_by_device_entity_id(
        self,
        testing_client: FlaskClient,  # noqa: F811
    ) -> None:
        """Filtering by device_entity_id returns only matching subscription."""
        response = testing_client.get(
            "/api/testing/devices/logs/subscriptions",
            query_string={"device_entity_id": "device_a"},
        )

        assert response.status_code == 200
        data = response.get_json()
        subs = data["subscriptions"]
        assert len(subs) == 1
        assert subs[0]["device_entity_id"] == "device_a"
        assert sorted(subs[0]["request_ids"]) == ["req-1", "req-2"]

    @pytest.mark.usefixtures("populate_subscriptions")
    def test_filter_nonexistent_device(
        self,
        testing_client: FlaskClient,  # noqa: F811
    ) -> None:
        """Filtering by nonexistent device_entity_id returns empty list."""
        response = testing_client.get(
            "/api/testing/devices/logs/subscriptions",
            query_string={"device_entity_id": "does_not_exist"},
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data["subscriptions"] == []


# ===========================================================================
# POST /api/testing/rotation/nudge
# ===========================================================================


class TestRotationNudge:
    """Tests for the rotation nudge endpoint."""

    def test_nudge_success(
        self,
        testing_client: FlaskClient,  # noqa: F811
        rotation_nudge_service: RotationNudgeService,
    ) -> None:
        """Nudge endpoint returns accepted and calls broadcast()."""
        with patch.object(
            rotation_nudge_service, "broadcast", return_value=True
        ) as mock_broadcast:
            response = testing_client.post("/api/testing/rotation/nudge")

        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "accepted"

        mock_broadcast.assert_called_once_with(source="testing")

    def test_nudge_with_empty_body(
        self,
        testing_client: FlaskClient,  # noqa: F811
        rotation_nudge_service: RotationNudgeService,
    ) -> None:
        """Nudge endpoint accepts empty JSON body."""
        with patch.object(
            rotation_nudge_service, "broadcast", return_value=True
        ) as mock_broadcast:
            response = testing_client.post(
                "/api/testing/rotation/nudge",
                json={},
            )

        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "accepted"
        mock_broadcast.assert_called_once_with(source="testing")

    def test_nudge_broadcast_returns_false(
        self,
        testing_client: FlaskClient,  # noqa: F811
        rotation_nudge_service: RotationNudgeService,
    ) -> None:
        """Nudge endpoint still returns accepted even when no clients received the event."""
        with patch.object(
            rotation_nudge_service, "broadcast", return_value=False
        ):
            response = testing_client.post("/api/testing/rotation/nudge")

        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "accepted"
