"""Pipeline API endpoints for CI/CD integration."""

import logging
import time
from typing import Any

from dependency_injector.wiring import Provide, inject
from flask import Blueprint, request
from spectree import Response as SpectreeResponse

from app.exceptions import RecordNotFoundException
from app.schemas.device_model import DeviceModelFirmwareResponseSchema
from app.schemas.error import ErrorResponseSchema
from app.schemas.pipeline import FirmwareVersionResponseSchema
from app.services.container import ServiceContainer
from app.services.device_model_service import DeviceModelService
from app.services.metrics_service import MetricsService
from app.utils.auth import allow_roles
from app.utils.error_handling import handle_api_errors
from app.utils.spectree_config import api

logger = logging.getLogger(__name__)

pipeline_bp = Blueprint("pipeline", __name__, url_prefix="/pipeline")


@pipeline_bp.route("/models/<string:code>/firmware", methods=["POST"])
@api.validate(
    resp=SpectreeResponse(
        HTTP_200=DeviceModelFirmwareResponseSchema,
        HTTP_400=ErrorResponseSchema,
        HTTP_404=ErrorResponseSchema,
    )
)
@handle_api_errors
@allow_roles("pipeline")
@inject
def upload_firmware(
    code: str,
    device_model_service: DeviceModelService = Provide[ServiceContainer.device_model_service],
    metrics_service: MetricsService = Provide[ServiceContainer.metrics_service],
) -> Any:
    """Upload firmware binary for a device model by code.

    Expects raw binary content in request body or multipart file upload.
    The firmware must be a valid ESP32 binary with AppInfo header.

    Args:
        code: Device model code (e.g., 'tempsensor')
    """
    start_time = time.perf_counter()
    status = "success"

    try:
        # Look up model by code
        model = device_model_service.get_device_model_by_code(code)

        # Handle multipart file upload or raw body
        if request.files and "file" in request.files:
            file = request.files["file"]
            content = file.read()
        else:
            content = request.get_data()

        if not content:
            from app.exceptions import ValidationException
            raise ValidationException("No firmware content provided")

        model = device_model_service.upload_firmware(model.id, content)

        logger.info(
            "Pipeline uploaded firmware for model %s: version %s",
            code,
            model.firmware_version,
        )

        return DeviceModelFirmwareResponseSchema.model_validate(model).model_dump()

    except Exception:
        status = "error"
        raise

    finally:
        duration = time.perf_counter() - start_time
        metrics_service.record_operation("pipeline_upload_firmware", status, duration)


@pipeline_bp.route("/models/<string:code>/firmware-version", methods=["GET"])
@api.validate(
    resp=SpectreeResponse(
        HTTP_200=FirmwareVersionResponseSchema,
        HTTP_404=ErrorResponseSchema,
    )
)
@handle_api_errors
@allow_roles("pipeline")
@inject
def get_firmware_version(
    code: str,
    device_model_service: DeviceModelService = Provide[ServiceContainer.device_model_service],
) -> Any:
    """Get the current firmware version for a device model.

    Useful for CI/CD pipelines to check if firmware needs to be uploaded.

    Args:
        code: Device model code (e.g., 'tempsensor')
    """
    model = device_model_service.get_device_model_by_code(code)
    if model is None:
        raise RecordNotFoundException(f"Device model with code '{code}' not found")

    return FirmwareVersionResponseSchema(
        code=model.code,
        firmware_version=model.firmware_version,
    ).model_dump()
