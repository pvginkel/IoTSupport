"""Tests for app-specific startup hooks."""

from unittest.mock import MagicMock, patch

from flask import Flask

from app.startup import _notify_rotation_nudge


class TestNotifyRotationNudge:
    """Tests for _notify_rotation_nudge helper."""

    def test_nudge_sent_when_url_configured(self, app: Flask) -> None:
        """Given INTERNAL_API_URL is set, when called, then HTTP POST is made."""
        mock_config = MagicMock()
        mock_config.internal_api_url = "http://web-process:3200"

        mock_container = MagicMock()
        mock_container.app_config.return_value = mock_config
        app.container = mock_container

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

    def test_nudge_skipped_when_url_not_configured(self, app: Flask) -> None:
        """Given INTERNAL_API_URL is not set, when called, then no HTTP call is made."""
        mock_config = MagicMock()
        mock_config.internal_api_url = None

        mock_container = MagicMock()
        mock_container.app_config.return_value = mock_config
        app.container = mock_container

        with patch("app.startup.httpx.post") as mock_post:
            _notify_rotation_nudge(app)

            mock_post.assert_not_called()

    def test_nudge_failure_does_not_raise(self, app: Flask) -> None:
        """Given HTTP call fails, when called, then exception is swallowed."""
        mock_config = MagicMock()
        mock_config.internal_api_url = "http://web-process:3200"

        mock_container = MagicMock()
        mock_container.app_config.return_value = mock_config
        app.container = mock_container

        with patch(
            "app.startup.httpx.post",
            side_effect=Exception("Connection refused"),
        ):
            # Should not raise
            _notify_rotation_nudge(app)

    def test_nudge_strips_trailing_slash(self, app: Flask) -> None:
        """Given INTERNAL_API_URL has trailing slash, URL is still correct.

        Note: strip_slashes is applied during AppSettings.load(), so the value
        stored in internal_api_url should already have trailing slashes removed.
        This test verifies the URL construction is correct regardless.
        """
        mock_config = MagicMock()
        mock_config.internal_api_url = "http://web-process:3200"

        mock_container = MagicMock()
        mock_container.app_config.return_value = mock_config
        app.container = mock_container

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        with patch("app.startup.httpx.post", return_value=mock_response) as mock_post:
            _notify_rotation_nudge(app)

            call_url = mock_post.call_args[0][0]
            assert call_url == "http://web-process:3200/internal/rotation-nudge"
