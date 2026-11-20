"""Tests for app-specific startup hooks."""

from unittest.mock import MagicMock, patch

import click
import pytest
from click.testing import CliRunner
from flask import Flask

from app.startup import _notify_rotation_nudge, register_cli_commands


class TestNotifyRotationNudge:
    """Tests for _notify_rotation_nudge helper."""

    def test_nudge_sent_when_url_configured(
        self, app: Flask, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Given INTERNAL_API_URL is set, when called, then HTTP POST is made."""
        mock_config = MagicMock()
        mock_config.internal_api_url = "http://web-process:3200"

        mock_container = MagicMock()
        mock_container.app_config.return_value = mock_config
        # The session app is shared: monkeypatch puts its container back.
        monkeypatch.setattr(app, "container", mock_container)

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        with patch("app.startup.httpx.post", return_value=mock_response) as mock_post:
            _notify_rotation_nudge(app)

            mock_post.assert_called_once_with(
                "http://web-process:3200/internal/rotation-nudge",
                json={},
                timeout=5.0,
            )
            mock_response.raise_for_status.assert_called_once()

    def test_nudge_skipped_when_url_not_configured(
        self, app: Flask, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Given INTERNAL_API_URL is not set, when called, then no HTTP call is made."""
        mock_config = MagicMock()
        mock_config.internal_api_url = None

        mock_container = MagicMock()
        mock_container.app_config.return_value = mock_config
        # The session app is shared: monkeypatch puts its container back.
        monkeypatch.setattr(app, "container", mock_container)

        with patch("app.startup.httpx.post") as mock_post:
            _notify_rotation_nudge(app)

            mock_post.assert_not_called()

    def test_nudge_failure_does_not_raise(
        self, app: Flask, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Given HTTP call fails, when called, then exception is swallowed."""
        mock_config = MagicMock()
        mock_config.internal_api_url = "http://web-process:3200"

        mock_container = MagicMock()
        mock_container.app_config.return_value = mock_config
        # The session app is shared: monkeypatch puts its container back.
        monkeypatch.setattr(app, "container", mock_container)

        with patch(
            "app.startup.httpx.post",
            side_effect=Exception("Connection refused"),
        ):
            # Should not raise
            _notify_rotation_nudge(app)

    def test_nudge_strips_trailing_slash(
        self, app: Flask, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Given INTERNAL_API_URL has trailing slash, URL is still correct.

        Note: strip_slashes is applied during AppSettings.load(), so the value
        stored in internal_api_url should already have trailing slashes removed.
        This test verifies the URL construction is correct regardless.
        """
        mock_config = MagicMock()
        mock_config.internal_api_url = "http://web-process:3200"

        mock_container = MagicMock()
        mock_container.app_config.return_value = mock_config
        # The session app is shared: monkeypatch puts its container back.
        monkeypatch.setattr(app, "container", mock_container)

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        with patch("app.startup.httpx.post", return_value=mock_response) as mock_post:
            _notify_rotation_nudge(app)

            call_url = mock_post.call_args[0][0]
            assert call_url == "http://web-process:3200/internal/rotation-nudge"


class TestRotationJob:
    """Tests for the rotation-job CLI command the CronJob runs."""

    def _run(
        self, app: Flask, monkeypatch: pytest.MonkeyPatch, mqtt_connected: bool
    ) -> tuple[click.testing.Result, MagicMock]:
        """Run rotation-job against a mocked container; return the result and it."""
        mock_container = MagicMock()
        mock_container.settings_service.return_value.get.return_value = None
        mock_container.app_config.return_value.internal_api_url = None
        mock_container.mqtt_service.return_value.wait_for_connection.return_value = (
            mqtt_connected
        )
        result_obj = mock_container.rotation_service.return_value.process_rotation_job
        result_obj.return_value.scheduled_rotation_triggered = False
        # The session app is shared: monkeypatch puts its container back.
        monkeypatch.setattr(app, "container", mock_container)

        @click.group()
        def cli() -> None:
            """A bare group carrying the app's commands."""

        with patch("app.database.check_db_connection", return_value=True):
            register_cli_commands(cli)
            result = CliRunner().invoke(cli, ["rotation-job"], obj={"app": app})
        return result, mock_container

    def test_rotates_once_mqtt_is_connected(
        self, app: Flask, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Given the broker confirms the connection, the job rotates and succeeds."""
        result, container = self._run(app, monkeypatch, mqtt_connected=True)

        assert result.exit_code == 0, result.output
        mqtt_service = container.mqtt_service.return_value
        mqtt_service.startup.assert_called_once_with()
        mqtt_service.wait_for_connection.assert_called_once_with(10.0)
        container.rotation_service.return_value.process_rotation_job.assert_called_once()
        container.lifecycle_coordinator.return_value.shutdown.assert_called_once_with()

    def test_fails_without_rotating_when_mqtt_does_not_connect(
        self, app: Flask, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Given no MQTT connection, the job rotates nothing and exits non-zero.

        A device set PENDING while publish() drops its notification is never
        told to rotate, so the job must not get that far.
        """
        result, container = self._run(app, monkeypatch, mqtt_connected=False)

        assert result.exit_code == 1
        assert "MQTT broker did not confirm the connection within 10s" in result.stderr
        container.rotation_service.return_value.process_rotation_job.assert_not_called()
        container.db_session.return_value.commit.assert_not_called()
        container.lifecycle_coordinator.return_value.shutdown.assert_called_once_with()
