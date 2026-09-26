"""Tests for ArchitecturePipelineTriggerService."""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.app_config import AppSettings
from app.services.architecture_pipeline_trigger_service import (
    ArchitecturePipelineTriggerService,
)
from app.utils.after_commit import (
    clear_after_commit_callbacks,
    run_after_commit_callbacks,
)


@pytest.fixture(autouse=True)
def _reset_after_commit():
    """Ensure no after_commit callbacks leak between tests."""
    clear_after_commit_callbacks()
    yield
    clear_after_commit_callbacks()


def _settings(url: str | None) -> AppSettings:
    return AppSettings(architecture_pipeline_trigger_url=url)


class TestArchitecturePipelineTriggerService:
    """Behavioral tests for the best-effort trigger."""

    def test_disabled_when_url_unset(self) -> None:
        service = ArchitecturePipelineTriggerService(_settings(None))
        assert service.enabled is False

    def test_enabled_when_url_set(self) -> None:
        service = ArchitecturePipelineTriggerService(_settings("https://ci.local/hook?token=x"))
        assert service.enabled is True

    def test_no_mark_pending_no_post(self) -> None:
        """Without mark_pending, committing fires nothing even when enabled."""
        service = ArchitecturePipelineTriggerService(_settings("https://ci.local/hook"))
        with patch.object(service._http_client, "post") as mock_post:
            run_after_commit_callbacks()
            mock_post.assert_not_called()

    def test_pending_but_url_unset_skips(self) -> None:
        """Marked pending but no URL -> skipped, no POST, no exception."""
        service = ArchitecturePipelineTriggerService(_settings(None))
        service.mark_pending()
        with patch.object(service._http_client, "post") as mock_post:
            run_after_commit_callbacks()
            mock_post.assert_not_called()

    def test_pending_and_enabled_posts_empty_body_once(self) -> None:
        """Marked pending twice + URL set -> exactly one empty-body POST."""
        url = "https://ci.local/hook?token=secret"
        service = ArchitecturePipelineTriggerService(_settings(url))
        service.mark_pending()
        service.mark_pending()

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        with patch.object(service._http_client, "post", return_value=mock_response) as mock_post:
            run_after_commit_callbacks()
            mock_post.assert_called_once_with(url)

    def test_fire_swallows_http_error(self) -> None:
        """A POST failure is swallowed (best-effort); no exception propagates."""
        service = ArchitecturePipelineTriggerService(_settings("https://ci.local/hook"))

        with patch.object(
            service._http_client,
            "post",
            side_effect=httpx.ConnectError("boom"),
        ) as mock_post:
            # Must not raise.
            service.fire()
            mock_post.assert_called_once()

    def test_cleared_callbacks_do_not_fire(self) -> None:
        """A rolled-back request clears the callbacks; nothing fires."""
        service = ArchitecturePipelineTriggerService(_settings("https://ci.local/hook"))
        service.mark_pending()
        clear_after_commit_callbacks()
        with patch.object(service._http_client, "post") as mock_post:
            run_after_commit_callbacks()
            mock_post.assert_not_called()
