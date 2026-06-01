"""Tests for ArchitecturePipelineTriggerService."""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.app_config import AppSettings
from app.services.architecture_pipeline_trigger_service import (
    ArchitecturePipelineTriggerService,
    _pending,
)


@pytest.fixture(autouse=True)
def _reset_pending():
    """Ensure the request-scoped pending flag is reset around each test."""
    _pending.set(False)
    yield
    _pending.set(False)


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

    def test_fire_when_not_pending_is_noop(self) -> None:
        """No mark_pending -> no POST even when enabled."""
        service = ArchitecturePipelineTriggerService(_settings("https://ci.local/hook"))
        with patch.object(service._http_client, "post") as mock_post:
            service.fire_if_pending()
            mock_post.assert_not_called()

    def test_fire_when_pending_but_url_unset_skips(self) -> None:
        """Marked pending but no URL -> skipped, no POST, no exception."""
        service = ArchitecturePipelineTriggerService(_settings(None))
        service.mark_pending()
        with patch.object(service._http_client, "post") as mock_post:
            service.fire_if_pending()
            mock_post.assert_not_called()

    def test_fire_when_pending_and_enabled_posts_empty_body(self) -> None:
        """Marked pending + URL set -> exactly one empty-body POST to the URL."""
        url = "https://ci.local/hook?token=secret"
        service = ArchitecturePipelineTriggerService(_settings(url))
        service.mark_pending()

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        with patch.object(service._http_client, "post", return_value=mock_response) as mock_post:
            service.fire_if_pending()
            mock_post.assert_called_once_with(url)

    def test_fire_swallows_http_error(self) -> None:
        """A POST failure is swallowed (best-effort); no exception propagates."""
        service = ArchitecturePipelineTriggerService(_settings("https://ci.local/hook"))
        service.mark_pending()

        with patch.object(
            service._http_client,
            "post",
            side_effect=httpx.ConnectError("boom"),
        ) as mock_post:
            # Must not raise.
            service.fire_if_pending()
            mock_post.assert_called_once()

    def test_clear_pending_resets_flag(self) -> None:
        service = ArchitecturePipelineTriggerService(_settings("https://ci.local/hook"))
        service.mark_pending()
        assert service.is_pending() is True
        service.clear_pending()
        assert service.is_pending() is False

    def test_fire_does_not_clear_flag(self) -> None:
        """fire_if_pending leaves the flag for teardown's finally to clear."""
        service = ArchitecturePipelineTriggerService(_settings("https://ci.local/hook"))
        service.mark_pending()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        with patch.object(service._http_client, "post", return_value=mock_response):
            service.fire_if_pending()
        assert service.is_pending() is True
