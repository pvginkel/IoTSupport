"""Rotation management API endpoints."""

import time
from typing import Any

from dependency_injector.wiring import Provide, inject
from flask import Blueprint
from spectree import Response as SpectreeResponse

from app.schemas.error import ErrorResponseSchema
from app.schemas.rotation import (
    DashboardResponseSchema,
    RotationStatusSchema,
    RotationTriggerResponseSchema,
)
from app.services.container import ServiceContainer
from app.services.metrics_service import MetricsService
from app.services.rotation_service import RotationService
from app.utils.error_handling import handle_api_errors
from app.utils.spectree_config import api

rotation_bp = Blueprint("rotation", __name__, url_prefix="/rotation")


@rotation_bp.route("/status", methods=["GET"])
@api.validate(resp=SpectreeResponse(HTTP_200=RotationStatusSchema))
@handle_api_errors
@inject
def get_rotation_status(
    rotation_service: RotationService = Provide[ServiceContainer.rotation_service],
    metrics_service: MetricsService = Provide[ServiceContainer.metrics_service],
) -> Any:
    """Get current rotation status across all devices.

    Returns counts by state, currently pending device, and last completion time.
    """
    start_time = time.perf_counter()
    status = "success"

    try:
        result = rotation_service.get_rotation_status()
        return RotationStatusSchema(**result).model_dump()

    except Exception:
        status = "error"
        raise

    finally:
        duration = time.perf_counter() - start_time
        metrics_service.record_operation("get_rotation_status", status, duration)


@rotation_bp.route("/trigger", methods=["POST"])
@api.validate(
    resp=SpectreeResponse(
        HTTP_200=RotationTriggerResponseSchema,
        HTTP_500=ErrorResponseSchema,
    )
)
@handle_api_errors
@inject
def trigger_fleet_rotation(
    rotation_service: RotationService = Provide[ServiceContainer.rotation_service],
    metrics_service: MetricsService = Provide[ServiceContainer.metrics_service],
) -> Any:
    """Manually trigger fleet-wide rotation.

    Queues all devices with OK state for rotation and immediately
    starts rotating the first device. Chain rotation handles the rest.
    """
    start_time = time.perf_counter()
    status = "success"

    try:
        queued_count = rotation_service.trigger_fleet_rotation()

        # Start rotating immediately instead of waiting for CRON job
        if queued_count > 0:
            rotation_service.rotate_next_queued_device()

        return RotationTriggerResponseSchema(queued_count=queued_count).model_dump()

    except Exception:
        status = "error"
        raise

    finally:
        duration = time.perf_counter() - start_time
        metrics_service.record_operation("trigger_fleet_rotation", status, duration)


@rotation_bp.route("/dashboard", methods=["GET"])
@api.validate(resp=SpectreeResponse(HTTP_200=DashboardResponseSchema))
@handle_api_errors
@inject
def get_dashboard(
    rotation_service: RotationService = Provide[ServiceContainer.rotation_service],
    metrics_service: MetricsService = Provide[ServiceContainer.metrics_service],
) -> Any:
    """Get device dashboard grouped by health status.

    Returns devices categorized as:
    - healthy: OK, QUEUED, or PENDING states
    - warning: TIMEOUT state, under critical threshold
    - critical: TIMEOUT state, at or over critical threshold
    """
    start_time = time.perf_counter()
    status = "success"

    try:
        result = rotation_service.get_dashboard_status()
        return DashboardResponseSchema(**result).model_dump()

    except Exception:
        status = "error"
        raise

    finally:
        duration = time.perf_counter() - start_time
        metrics_service.record_operation("get_dashboard", status, duration)
