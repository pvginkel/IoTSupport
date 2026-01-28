"""Device model management API endpoints."""

import json
import time
from typing import Any

from dependency_injector.wiring import Provide, inject
from flask import Blueprint, request, send_file
from spectree import Response as SpectreeResponse

from app.schemas.device_model import (
    DeviceModelCreateSchema,
    DeviceModelFirmwareResponseSchema,
    DeviceModelListResponseSchema,
    DeviceModelResponseSchema,
    DeviceModelSummarySchema,
    DeviceModelUpdateSchema,
)
from app.schemas.error import ErrorResponseSchema
from app.services.container import ServiceContainer
from app.services.device_model_service import DeviceModelService
from app.services.metrics_service import MetricsService
from app.services.mqtt_service import MqttService
from app.utils.error_handling import handle_api_errors
from app.utils.spectree_config import api

device_models_bp = Blueprint("device_models", __name__, url_prefix="/device-models")


@device_models_bp.route("", methods=["GET"])
@api.validate(resp=SpectreeResponse(HTTP_200=DeviceModelListResponseSchema))
@handle_api_errors
@inject
def list_device_models(
    device_model_service: DeviceModelService = Provide[ServiceContainer.device_model_service],
    metrics_service: MetricsService = Provide[ServiceContainer.metrics_service],
) -> Any:
    """List all device models."""
    start_time = time.perf_counter()
    status = "success"

    try:
        models = device_model_service.list_device_models()

        summaries = [
            DeviceModelSummarySchema.model_validate(m) for m in models
        ]

        return DeviceModelListResponseSchema(
            device_models=summaries, count=len(models)
        ).model_dump()

    except Exception:
        status = "error"
        raise

    finally:
        duration = time.perf_counter() - start_time
        metrics_service.record_operation("list_device_models", status, duration)


@device_models_bp.route("", methods=["POST"])
@api.validate(
    json=DeviceModelCreateSchema,
    resp=SpectreeResponse(
        HTTP_201=DeviceModelResponseSchema,
        HTTP_400=ErrorResponseSchema,
        HTTP_409=ErrorResponseSchema,
    ),
)
@handle_api_errors
@inject
def create_device_model(
    device_model_service: DeviceModelService = Provide[ServiceContainer.device_model_service],
    metrics_service: MetricsService = Provide[ServiceContainer.metrics_service],
) -> Any:
    """Create a new device model."""
    start_time = time.perf_counter()
    status = "success"

    try:
        data = DeviceModelCreateSchema.model_validate(request.get_json())
        model = device_model_service.create_device_model(
            code=data.code,
            name=data.name,
            config_schema=data.config_schema,
        )

        return DeviceModelResponseSchema.model_validate(model).model_dump(), 201

    except Exception:
        status = "error"
        raise

    finally:
        duration = time.perf_counter() - start_time
        metrics_service.record_operation("create_device_model", status, duration)


@device_models_bp.route("/<int:model_id>", methods=["GET"])
@api.validate(
    resp=SpectreeResponse(
        HTTP_200=DeviceModelResponseSchema,
        HTTP_404=ErrorResponseSchema,
    )
)
@handle_api_errors
@inject
def get_device_model(
    model_id: int,
    device_model_service: DeviceModelService = Provide[ServiceContainer.device_model_service],
    metrics_service: MetricsService = Provide[ServiceContainer.metrics_service],
) -> Any:
    """Get a device model by ID."""
    start_time = time.perf_counter()
    status = "success"

    try:
        model = device_model_service.get_device_model(model_id)
        return DeviceModelResponseSchema.model_validate(model).model_dump()

    except Exception:
        status = "error"
        raise

    finally:
        duration = time.perf_counter() - start_time
        metrics_service.record_operation("get_device_model", status, duration)


@device_models_bp.route("/<int:model_id>", methods=["PUT"])
@api.validate(
    json=DeviceModelUpdateSchema,
    resp=SpectreeResponse(
        HTTP_200=DeviceModelResponseSchema,
        HTTP_400=ErrorResponseSchema,
        HTTP_404=ErrorResponseSchema,
    ),
)
@handle_api_errors
@inject
def update_device_model(
    model_id: int,
    device_model_service: DeviceModelService = Provide[ServiceContainer.device_model_service],
    metrics_service: MetricsService = Provide[ServiceContainer.metrics_service],
) -> Any:
    """Update a device model."""
    start_time = time.perf_counter()
    status = "success"

    try:
        data = DeviceModelUpdateSchema.model_validate(request.get_json())
        model = device_model_service.update_device_model(
            model_id,
            name=data.name,
            config_schema=data.config_schema,
        )

        return DeviceModelResponseSchema.model_validate(model).model_dump()

    except Exception:
        status = "error"
        raise

    finally:
        duration = time.perf_counter() - start_time
        metrics_service.record_operation("update_device_model", status, duration)


@device_models_bp.route("/<int:model_id>", methods=["DELETE"])
@api.validate(
    resp=SpectreeResponse(
        HTTP_204=None,
        HTTP_404=ErrorResponseSchema,
        HTTP_409=ErrorResponseSchema,
    )
)
@handle_api_errors
@inject
def delete_device_model(
    model_id: int,
    device_model_service: DeviceModelService = Provide[ServiceContainer.device_model_service],
    metrics_service: MetricsService = Provide[ServiceContainer.metrics_service],
) -> Any:
    """Delete a device model."""
    start_time = time.perf_counter()
    status = "success"

    try:
        device_model_service.delete_device_model(model_id)
        return "", 204

    except Exception:
        status = "error"
        raise

    finally:
        duration = time.perf_counter() - start_time
        metrics_service.record_operation("delete_device_model", status, duration)


@device_models_bp.route("/<int:model_id>/firmware", methods=["POST"])
@api.validate(
    resp=SpectreeResponse(
        HTTP_200=DeviceModelFirmwareResponseSchema,
        HTTP_400=ErrorResponseSchema,
        HTTP_404=ErrorResponseSchema,
    )
)
@handle_api_errors
@inject
def upload_firmware(
    model_id: int,
    device_model_service: DeviceModelService = Provide[ServiceContainer.device_model_service],
    metrics_service: MetricsService = Provide[ServiceContainer.metrics_service],
    mqtt_service: MqttService = Provide[ServiceContainer.mqtt_service],
) -> Any:
    """Upload firmware binary for a device model.

    Expects raw binary content in request body or multipart file upload.
    The firmware must be a valid ESP32 binary with AppInfo header.
    """
    start_time = time.perf_counter()
    status = "success"

    try:
        # Handle multipart file upload or raw body
        if request.files and "file" in request.files:
            file = request.files["file"]
            content = file.read()
        else:
            content = request.get_data()

        if not content:
            from app.exceptions import ValidationException
            raise ValidationException("No firmware content provided")

        model = device_model_service.upload_firmware(model_id, content)

        # Publish MQTT notification for each device using this model
        for device in model.devices:
            payload = json.dumps({
                "client_id": device.client_id,
                "firmware_version": model.firmware_version,
            })
            mqtt_service.publish(f"{MqttService.TOPIC_UPDATES}/firmware", payload)

        return DeviceModelFirmwareResponseSchema.model_validate(model).model_dump()

    except Exception:
        status = "error"
        raise

    finally:
        duration = time.perf_counter() - start_time
        metrics_service.record_operation("upload_firmware", status, duration)


@device_models_bp.route("/<int:model_id>/firmware", methods=["GET"])
@handle_api_errors
@inject
def download_firmware(
    model_id: int,
    device_model_service: DeviceModelService = Provide[ServiceContainer.device_model_service],
    metrics_service: MetricsService = Provide[ServiceContainer.metrics_service],
) -> Any:
    """Download firmware binary for a device model.

    Returns raw binary firmware with appropriate content type.
    """
    start_time = time.perf_counter()
    status = "success"

    try:
        stream, model_code = device_model_service.get_firmware_stream(model_id)

        # Use send_file with BytesIO stream
        return send_file(
            stream,
            mimetype="application/octet-stream",
            as_attachment=True,
            download_name=f"firmware-{model_code}.bin",
        )

    except Exception:
        status = "error"
        raise

    finally:
        duration = time.perf_counter() - start_time
        metrics_service.record_operation("download_firmware", status, duration)
