"""Architecture pipeline trigger service.

Best-effort outbound trigger that asks the architecture CI job to regenerate
the deployed-architecture artifact after the fleet changes.

Admin CRUD service methods call :meth:`mark_pending` after a successful
device/model write. That registers :meth:`fire` with the template's
``after_commit()``, so the trigger fires once per request, only after the DB
transaction is durable, and never on rollback. This matches the project's
"commit before external side effect" ordering: the regenerating GET will see the
committed rows, and a rolled-back write never fires a trigger.

The POST is fire-and-forget: failures are logged (host only, never the full URL
which may embed a webhook token) and swallowed so they never affect the write.
"""

import logging
import time
from typing import TYPE_CHECKING
from urllib.parse import urlparse

import httpx

from app.utils.after_commit import after_commit
from app.utils.iot_metrics import record_operation

if TYPE_CHECKING:
    from app.app_config import AppSettings

logger = logging.getLogger(__name__)


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
        """Fire the trigger once the current request has committed.

        Idempotent within a request: many writes coalesce into a single trigger
        fired post-commit. Does not perform any I/O.
        """
        after_commit(self.fire)

    def fire(self) -> None:
        """POST to the trigger URL, if one is configured.

        Best-effort: all errors are logged and swallowed.
        """
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
