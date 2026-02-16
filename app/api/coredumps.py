"""Coredump management API endpoints.

Admin endpoints for viewing, downloading, and deleting coredumps,
nested under /devices/<device_id>/coredumps.
"""

import time
from typing import Any

from dependency_injector.wiring import Provide, inject
from flask import Blueprint, send_file
from spectree import Response as SpectreeResponse

from app.schemas.coredump import (
    CoredumpDetailSchema,
    CoredumpListResponseSchema,
    CoredumpSummarySchema,
)
from app.schemas.error import ErrorResponseSchema
from app.services.container import ServiceContainer
from app.services.coredump_service import CoredumpService
from app.services.device_service import DeviceService
from app.utils.error_handling import handle_api_errors
from app.utils.iot_metrics import record_operation
from app.utils.spectree_config import api

coredumps_bp = Blueprint("coredumps", __name__, url_prefix="/devices")


@coredumps_bp.route("/<int:device_id>/coredumps", methods=["GET"])
@api.validate(
    resp=SpectreeResponse(
        HTTP_200=CoredumpListResponseSchema,
        HTTP_404=ErrorResponseSchema,
    )
)
@handle_api_errors
@inject
def list_coredumps(
    device_id: int,
    device_service: DeviceService = Provide[ServiceContainer.device_service],
    coredump_service: CoredumpService = Provide[ServiceContainer.coredump_service],

) -> Any:
    """List all coredumps for a device."""
    start_time = time.perf_counter()
    status = "success"

    try:
        # Verify device exists (raises RecordNotFoundException if not)
        device_service.get_device(device_id)

        coredumps = coredump_service.list_coredumps(device_id)
        summaries = [CoredumpSummarySchema.model_validate(c) for c in coredumps]

        return CoredumpListResponseSchema(
            coredumps=summaries, count=len(coredumps)
        ).model_dump(mode="json")

    except Exception:
        status = "error"
        raise

    finally:
        duration = time.perf_counter() - start_time
        record_operation("list_coredumps", status, duration)


@coredumps_bp.route("/<int:device_id>/coredumps/<int:coredump_id>", methods=["GET"])
@api.validate(
    resp=SpectreeResponse(
        HTTP_200=CoredumpDetailSchema,
        HTTP_404=ErrorResponseSchema,
    )
)
@handle_api_errors
@inject
def get_coredump(
    device_id: int,
    coredump_id: int,
    coredump_service: CoredumpService = Provide[ServiceContainer.coredump_service],

) -> Any:
    """Get coredump detail including parsed output."""
    start_time = time.perf_counter()
    status = "success"

    try:
        coredump = coredump_service.get_coredump(device_id, coredump_id)
        return CoredumpDetailSchema.model_validate(coredump).model_dump(mode="json")

    except Exception:
        status = "error"
        raise

    finally:
        duration = time.perf_counter() - start_time
        record_operation("get_coredump", status, duration)


@coredumps_bp.route(
    "/<int:device_id>/coredumps/<int:coredump_id>/download", methods=["GET"]
)
@handle_api_errors
@inject
def download_coredump(
    device_id: int,
    coredump_id: int,
    device_service: DeviceService = Provide[ServiceContainer.device_service],
    coredump_service: CoredumpService = Provide[ServiceContainer.coredump_service],

) -> Any:
    """Download raw coredump .dmp binary from S3."""
    start_time = time.perf_counter()
    status = "success"

    try:
        # Get the coredump record (verifies ownership)
        coredump = coredump_service.get_coredump(device_id, coredump_id)

        # Resolve the device key for S3 path
        device = device_service.get_device(device_id)

        # Download from S3 as a BytesIO stream
        stream = coredump_service.get_coredump_stream(device.key, coredump.id)

        return send_file(  # type: ignore[call-arg]
            stream,
            mimetype="application/octet-stream",
            as_attachment=True,
            download_name=f"coredump_{coredump.id}.dmp",
        )

    except Exception:
        status = "error"
        raise

    finally:
        duration = time.perf_counter() - start_time
        record_operation("download_coredump", status, duration)


@coredumps_bp.route(
    "/<int:device_id>/coredumps/<int:coredump_id>", methods=["DELETE"]
)
@api.validate(
    resp=SpectreeResponse(
        HTTP_204=None,
        HTTP_404=ErrorResponseSchema,
    )
)
@handle_api_errors
@inject
def delete_coredump(
    device_id: int,
    coredump_id: int,
    device_service: DeviceService = Provide[ServiceContainer.device_service],
    coredump_service: CoredumpService = Provide[ServiceContainer.coredump_service],

) -> Any:
    """Delete a single coredump."""
    start_time = time.perf_counter()
    status = "success"

    try:
        device = device_service.get_device(device_id)
        coredump_service.delete_coredump(device_id, coredump_id, device.key)
        return "", 204

    except Exception:
        status = "error"
        raise

    finally:
        duration = time.perf_counter() - start_time
        record_operation("delete_coredump", status, duration)


@coredumps_bp.route("/<int:device_id>/coredumps", methods=["DELETE"])
@api.validate(
    resp=SpectreeResponse(
        HTTP_204=None,
        HTTP_404=ErrorResponseSchema,
    )
)
@handle_api_errors
@inject
def delete_all_coredumps(
    device_id: int,
    device_service: DeviceService = Provide[ServiceContainer.device_service],
    coredump_service: CoredumpService = Provide[ServiceContainer.coredump_service],

) -> Any:
    """Delete all coredumps for a device."""
    start_time = time.perf_counter()
    status = "success"

    try:
        device = device_service.get_device(device_id)
        coredump_service.delete_all_coredumps(device_id, device.key)
        return "", 204

    except Exception:
        status = "error"
        raise

    finally:
        duration = time.perf_counter() - start_time
        record_operation("delete_all_coredumps", status, duration)
