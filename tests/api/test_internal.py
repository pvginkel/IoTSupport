"""Tests for internal cluster-only API endpoints."""

from unittest.mock import patch

from flask.testing import FlaskClient

from app.services.container import ServiceContainer


class TestRotationNudge:
    """Tests for POST /internal/rotation-nudge."""

    def test_rotation_nudge_success(
        self, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Given active connections, when POST nudge, then 200 and broadcast is called."""
        rns = container.rotation_nudge_service()
        with patch.object(rns, "broadcast", return_value=True) as mock_nudge:
            response = client.post("/internal/rotation-nudge")

            assert response.status_code == 200
            data = response.get_json()
            assert data["status"] == "ok"

            mock_nudge.assert_called_once_with(source="cronjob")

    def test_rotation_nudge_no_connections(
        self, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Given no active connections, when POST nudge, then 200 (broadcast returns False)."""
        rns = container.rotation_nudge_service()
        with patch.object(rns, "broadcast", return_value=False) as mock_nudge:
            response = client.post("/internal/rotation-nudge")

            assert response.status_code == 200
            data = response.get_json()
            assert data["status"] == "ok"

            mock_nudge.assert_called_once_with(source="cronjob")
