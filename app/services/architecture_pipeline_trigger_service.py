"""Architecture pipeline trigger service.

Best-effort outbound trigger that asks the architecture CI job to regenerate
the deployed-architecture artifact after the fleet changes.

Two-step, request-scoped design (see feature plan §7):

1. Admin CRUD service methods call :meth:`mark_pending` after a successful
   device/model write. This sets a ``contextvars.ContextVar`` flag — NOT Flask
   ``g`` — so the service layer stays Flask-free.
2. ``teardown_request`` calls :meth:`fire_if_pending` ONLY on the commit-success
   branch (never on rollback), after the DB transaction is durable, then clears
   the flag. This matches the project's "commit before external side effect"
   ordering: the regenerating GET will see the committed rows, and a rolled-back
   write never fires a trigger.

The POST is fire-and-forget: failures are logged (host only, never the full URL
which may embed a webhook token) and swallowed so they never affect the write.
"""

import contextvars
import logging
import time
from typing import TYPE_CHECKING
from urllib.parse import urlparse

import httpx

from app.utils.iot_metrics import record_operation

if TYPE_CHECKING:
    from app.app_config import AppSettings

logger = logging.getLogger(__name__)

# Request-scoped "fleet dirty" flag. Set by mark_pending(), read+cleared by
# fire_if_pending() in teardown. A ContextVar is request-isolated and avoids a
# Flask dependency inside the service layer.
_pending: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "architecture_pipeline_pending", default=False
)


class ArchitecturePipelineTriggerService:
    """Singleton service that best-effort triggers the architecture CI job."""

    def __init__(self, config: "AppSettings") -> None:
        """Initialize the trigger service.

        Args:
            config: Application settings holding the (optional) trigger URL.
        """
        self.config = config
        # Short timeout: a slow/hung CI endpoint must not block the request.
        self._http_client = httpx.Client(timeout=5.0)

        # Gate on a truthy URL (mirrors KeycloakAdminService.enabled).
        self.enabled = bool(config.architecture_pipeline_trigger_url)

        if self.enabled:
            url = config.architecture_pipeline_trigger_url or ""
            logger.info(
                "ArchitecturePipelineTriggerService enabled (host: %s)",
                urlparse(url).hostname,
            )
        else:
            logger.info("ArchitecturePipelineTriggerService disabled - no trigger URL")

    def mark_pending(self) -> None:
        """Mark the current request as having changed the fleet.

        Idempotent within a request: many writes coalesce into a single trigger
        fired post-commit. Does not perform any I/O.
        """
        _pending.set(True)

    def is_pending(self) -> bool:
        """Return whether the current request has been marked fleet-dirty."""
        return _pending.get()

    def clear_pending(self) -> None:
        """Reset the request-scoped pending flag.

        Called from the teardown ``finally`` (mirrors ``db_session.reset()``)
        so the next request in the same context starts clean.
        """
        _pending.set(False)

    def fire_if_pending(self) -> None:
        """Fire the trigger iff the current request was marked fleet-dirty.

        Best-effort: only fires when (a) a write marked the request pending and
        (b) a trigger URL is configured. All errors are logged and swallowed.
        Does NOT clear the flag — the teardown ``finally`` owns that via
        :meth:`clear_pending`.
        """
        if not _pending.get():
            return

        if not self.enabled:
            # Marked dirty but no URL configured (dev/test) -> no-op.
            logger.debug("Architecture pipeline trigger pending but no URL configured")
            record_operation("architecture_pipeline_trigger", "skipped")
            return

        url = self.config.architecture_pipeline_trigger_url or ""
        host = urlparse(url).hostname
        start_time = time.perf_counter()

        try:
            # Empty-body POST; the URL itself carries any auth/token.
            response = self._http_client.post(url)
            response.raise_for_status()
            duration = time.perf_counter() - start_time
            logger.info(
                "Triggered architecture pipeline (host: %s) in %.3fs", host, duration
            )
            record_operation("architecture_pipeline_trigger", "success", duration)

        except Exception as e:
            duration = time.perf_counter() - start_time
            logger.warning(
                "Failed to trigger architecture pipeline (host: %s): %s (%.3fs)",
                host,
                e,
                duration,
            )
            record_operation("architecture_pipeline_trigger", "error", duration)
