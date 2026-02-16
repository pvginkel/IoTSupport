"""Internal cluster-only endpoints.

These endpoints are registered on '/' (not '/api/') to separate them
from the user-facing API. They are intended for intra-cluster
communication (e.g., CronJob -> web process notifications) and should
not be publicly proxied.
"""

import logging
from typing import Any

from dependency_injector.wiring import Provide, inject
from flask import Blueprint, jsonify

from app.services.container import ServiceContainer
from app.services.rotation_nudge_service import RotationNudgeService

logger = logging.getLogger(__name__)

internal_bp = Blueprint("internal", __name__, url_prefix="/internal")


@internal_bp.route("/rotation-nudge", methods=["POST"])
@inject
def rotation_nudge(
    rotation_nudge_service: RotationNudgeService = Provide[ServiceContainer.rotation_nudge_service],
) -> tuple[Any, int]:
    """Trigger a rotation-updated SSE broadcast.

    Called by the CronJob rotation_job after processing rotation changes
    in a separate process. The CronJob has no SSE connections, so it
    delegates the broadcast to the web process via this endpoint.

    Returns 200 regardless of whether any clients received the broadcast.
    """
    result = rotation_nudge_service.broadcast(source="cronjob")

    logger.info(
        "Internal rotation nudge triggered",
        extra={"delivered": result},
    )

    return jsonify({"status": "ok"}), 200
