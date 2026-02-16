"""Testing endpoints for device SSE log streaming and rotation nudge.

Provides endpoints for Playwright tests to:
- Inject log entries into the DeviceLogStreamService SSE pipeline
- Poll active SSE subscription state
- Broadcast rotation-updated SSE events

All endpoints are guarded by reject_if_not_testing() so they are
only available when FLASK_ENV=testing.
"""

import logging
from datetime import UTC, datetime
from typing import Any

from dependency_injector.wiring import Provide, inject
from flask import Blueprint, request
from spectree import Response as SpectreeResponse

from app.api.testing_guard import reject_if_not_testing
from app.schemas.testing_device_sse import (
    LogInjectRequestSchema,
    LogInjectResponseSchema,
    NudgeResponseSchema,
    SubscriptionsQuerySchema,
    SubscriptionsResponseSchema,
)
from app.services.container import ServiceContainer
from app.services.device_log_stream_service import DeviceLogStreamService
from app.services.rotation_nudge_service import RotationNudgeService
from app.utils.spectree_config import api

logger = logging.getLogger(__name__)

testing_device_sse_bp = Blueprint(
    "testing_device_sse", __name__, url_prefix="/api/testing"
)


@testing_device_sse_bp.before_request
def _guard() -> Any:
    return reject_if_not_testing()


# ---------------------------------------------------------------------------
# Log injection
# ---------------------------------------------------------------------------


@testing_device_sse_bp.route("/devices/logs/inject", methods=["POST"])
@api.validate(
    json=LogInjectRequestSchema,
    resp=SpectreeResponse(HTTP_200=LogInjectResponseSchema),
)
@inject
def inject_device_logs(
    device_log_stream_service: DeviceLogStreamService = Provide[
        ServiceContainer.device_log_stream_service
    ],
) -> tuple[dict[str, Any], int]:
    """Inject log entries into the SSE device-log pipeline.

    Constructs documents matching the shape of real MQTT-sourced log events
    and forwards them to DeviceLogStreamService.forward_logs(). If no SSE
    client is subscribed to the target device, logs are silently dropped.
    """
    data = LogInjectRequestSchema.model_validate(request.get_json())

    # Build enriched documents matching the shape expected by forward_logs()
    now = datetime.now(UTC).isoformat()
    documents: list[dict[str, Any]] = []
    for entry in data.logs:
        doc = entry.model_dump()
        doc["@timestamp"] = now
        doc["entity_id"] = data.device_entity_id
        documents.append(doc)

    device_log_stream_service.forward_logs(documents)

    logger.info(
        "Injected %d test log entries for device %s",
        len(documents),
        data.device_entity_id,
    )

    return LogInjectResponseSchema(
        status="accepted",
        forwarded=len(documents),
    ).model_dump(), 200


# ---------------------------------------------------------------------------
# Subscription status
# ---------------------------------------------------------------------------


@testing_device_sse_bp.route("/devices/logs/subscriptions", methods=["GET"])
@api.validate(
    query=SubscriptionsQuerySchema,
    resp=SpectreeResponse(HTTP_200=SubscriptionsResponseSchema),
)
@inject
def get_log_subscriptions(
    device_log_stream_service: DeviceLogStreamService = Provide[
        ServiceContainer.device_log_stream_service
    ],
) -> tuple[dict[str, Any], int]:
    """Return active SSE device-log subscriptions.

    Used by Playwright tests to poll-wait until a subscription is active
    before injecting logs.
    """
    query = SubscriptionsQuerySchema.model_validate(request.args.to_dict())
    subscriptions = device_log_stream_service.get_subscriptions(
        device_entity_id=query.device_entity_id,
    )

    return SubscriptionsResponseSchema.model_validate(
        {"subscriptions": subscriptions},
    ).model_dump(), 200


# ---------------------------------------------------------------------------
# Rotation nudge
# ---------------------------------------------------------------------------


@testing_device_sse_bp.route("/rotation/nudge", methods=["POST"])
@api.validate(
    resp=SpectreeResponse(HTTP_200=NudgeResponseSchema),
)
@inject
def nudge_rotation(
    rotation_nudge_service: RotationNudgeService = Provide[
        ServiceContainer.rotation_nudge_service
    ],
) -> tuple[dict[str, Any], int]:
    """Broadcast a rotation-updated SSE event to all connected clients.

    No rotation state is changed; this purely triggers the SSE-to-dashboard
    refresh path for Playwright testing.
    """
    rotation_nudge_service.broadcast(source="testing")

    logger.info("Broadcast rotation nudge from testing endpoint")

    return NudgeResponseSchema(status="accepted").model_dump(), 200
