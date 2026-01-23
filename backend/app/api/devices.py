"""Device management API endpoints."""

import time
from typing import Any

from dependency_injector.wiring import Provide, inject
from flask import Blueprint, request
from spectree import Response as SpectreeResponse

from app.schemas.device import (
    DeviceCreateSchema,
    DeviceKeycloakStatusSchema,
    DeviceListResponseSchema,
    DeviceResponseSchema,
    DeviceRotateResponseSchema,
    DeviceSummarySchema,
    DeviceUpdateSchema,
    NvsProvisioningQuerySchema,
    NvsProvisioningResponseSchema,
)
from app.schemas.error import ErrorResponseSchema
from app.services.container import ServiceContainer
from app.services.device_service import DeviceService
from app.services.metrics_service import MetricsService
from app.services.mqtt_service import MqttService
from app.utils.error_handling import handle_api_errors
from app.utils.spectree_config import api

devices_bp = Blueprint("devices", __name__, url_prefix="/devices")


@devices_bp.route("", methods=["GET"])
@api.validate(resp=SpectreeResponse(HTTP_200=DeviceListResponseSchema))
@handle_api_errors
@inject
def list_devices(
    device_service: DeviceService = Provide[ServiceContainer.device_service],
    metrics_service: MetricsService = Provide[ServiceContainer.metrics_service],
) -> Any:
    """List all devices with optional filtering."""
    start_time = time.perf_counter()
    status = "success"

    try:
        # Get optional query params
        model_id = request.args.get("model_id", type=int)
        rotation_state = request.args.get("rotation_state")

        devices = device_service.list_devices(
            model_id=model_id,
            rotation_state=rotation_state,
        )

        summaries = [DeviceSummarySchema.model_validate(d) for d in devices]

        return DeviceListResponseSchema(
            devices=summaries, count=len(devices)
        ).model_dump()

    except Exception:
        status = "error"
        raise

    finally:
        duration = time.perf_counter() - start_time
        metrics_service.record_operation("list_devices", status, duration)


@devices_bp.route("", methods=["POST"])
@api.validate(
    json=DeviceCreateSchema,
    resp=SpectreeResponse(
        HTTP_201=DeviceResponseSchema,
        HTTP_400=ErrorResponseSchema,
        HTTP_404=ErrorResponseSchema,
        HTTP_502=ErrorResponseSchema,
    ),
)
@handle_api_errors
@inject
def create_device(
    device_service: DeviceService = Provide[ServiceContainer.device_service],
    metrics_service: MetricsService = Provide[ServiceContainer.metrics_service],
) -> Any:
    """Create a new device with Keycloak client."""
    start_time = time.perf_counter()
    status = "success"

    try:
        data = DeviceCreateSchema.model_validate(request.get_json())
        device = device_service.create_device(
            device_model_id=data.device_model_id,
            config=data.config,
        )

        return DeviceResponseSchema.model_validate(device).model_dump(), 201

    except Exception:
        status = "error"
        raise

    finally:
        duration = time.perf_counter() - start_time
        metrics_service.record_operation("create_device", status, duration)


@devices_bp.route("/<int:device_id>", methods=["GET"])
@api.validate(
    resp=SpectreeResponse(
        HTTP_200=DeviceResponseSchema,
        HTTP_404=ErrorResponseSchema,
    )
)
@handle_api_errors
@inject
def get_device(
    device_id: int,
    device_service: DeviceService = Provide[ServiceContainer.device_service],
    metrics_service: MetricsService = Provide[ServiceContainer.metrics_service],
) -> Any:
    """Get a device by ID."""
    start_time = time.perf_counter()
    status = "success"

    try:
        device = device_service.get_device(device_id)
        return DeviceResponseSchema.model_validate(device).model_dump()

    except Exception:
        status = "error"
        raise

    finally:
        duration = time.perf_counter() - start_time
        metrics_service.record_operation("get_device", status, duration)


@devices_bp.route("/<int:device_id>", methods=["PUT"])
@api.validate(
    json=DeviceUpdateSchema,
    resp=SpectreeResponse(
        HTTP_200=DeviceResponseSchema,
        HTTP_400=ErrorResponseSchema,
        HTTP_404=ErrorResponseSchema,
    ),
)
@handle_api_errors
@inject
def update_device(
    device_id: int,
    device_service: DeviceService = Provide[ServiceContainer.device_service],
    metrics_service: MetricsService = Provide[ServiceContainer.metrics_service],
    mqtt_service: MqttService = Provide[ServiceContainer.mqtt_service],
) -> Any:
    """Update a device's configuration."""
    start_time = time.perf_counter()
    status = "success"

    try:
        data = DeviceUpdateSchema.model_validate(request.get_json())
        device = device_service.update_device(device_id, config=data.config)

        # Publish MQTT notification for config update
        mqtt_service.publish_config_update(f"{device.client_id}")

        return DeviceResponseSchema.model_validate(device).model_dump()

    except Exception:
        status = "error"
        raise

    finally:
        duration = time.perf_counter() - start_time
        metrics_service.record_operation("update_device", status, duration)


@devices_bp.route("/<int:device_id>", methods=["DELETE"])
@api.validate(
    resp=SpectreeResponse(
        HTTP_204=None,
        HTTP_404=ErrorResponseSchema,
        HTTP_502=ErrorResponseSchema,
    )
)
@handle_api_errors
@inject
def delete_device(
    device_id: int,
    device_service: DeviceService = Provide[ServiceContainer.device_service],
    metrics_service: MetricsService = Provide[ServiceContainer.metrics_service],
) -> Any:
    """Delete a device and its Keycloak client."""
    start_time = time.perf_counter()
    status = "success"

    try:
        device_service.delete_device(device_id)
        return "", 204

    except Exception:
        status = "error"
        raise

    finally:
        duration = time.perf_counter() - start_time
        metrics_service.record_operation("delete_device", status, duration)


@devices_bp.route("/<int:device_id>/provisioning", methods=["GET"])
@api.validate(
    query=NvsProvisioningQuerySchema,
    resp=SpectreeResponse(
        HTTP_200=NvsProvisioningResponseSchema,
        HTTP_404=ErrorResponseSchema,
        HTTP_502=ErrorResponseSchema,
    )
)
@handle_api_errors
@inject
def get_provisioning(
    device_id: int,
    device_service: DeviceService = Provide[ServiceContainer.device_service],
    metrics_service: MetricsService = Provide[ServiceContainer.metrics_service],
) -> Any:
    """Get NVS provisioning package for a device.

    Returns JSON containing an NVS binary blob that can be flashed
    directly to ESP32 devices using esptool-js or similar tools.

    The partition_size query parameter must match the NVS partition size
    in the device's partition table.
    """
    start_time = time.perf_counter()
    status = "success"

    try:
        query = NvsProvisioningQuerySchema.model_validate(request.args.to_dict())
        package = device_service.get_provisioning_package(
            device_id, partition_size=query.partition_size
        )
        return NvsProvisioningResponseSchema.model_validate(package).model_dump()

    except Exception:
        status = "error"
        raise

    finally:
        duration = time.perf_counter() - start_time
        metrics_service.record_operation("get_provisioning", status, duration)


@devices_bp.route("/<int:device_id>/rotate", methods=["POST"])
@api.validate(
    resp=SpectreeResponse(
        HTTP_200=DeviceRotateResponseSchema,
        HTTP_404=ErrorResponseSchema,
    )
)
@handle_api_errors
@inject
def trigger_device_rotation(
    device_id: int,
    device_service: DeviceService = Provide[ServiceContainer.device_service],
    metrics_service: MetricsService = Provide[ServiceContainer.metrics_service],
) -> Any:
    """Trigger rotation for a single device.

    Queues the device for credential rotation. If already pending, returns
    the current status without changing state.
    """
    start_time = time.perf_counter()
    status = "success"

    try:
        result = device_service.trigger_rotation(device_id)
        return DeviceRotateResponseSchema(status=result).model_dump()

    except Exception:
        status = "error"
        raise

    finally:
        duration = time.perf_counter() - start_time
        metrics_service.record_operation("trigger_device_rotation", status, duration)


@devices_bp.route("/<int:device_id>/keycloak-status", methods=["GET"])
@api.validate(
    resp=SpectreeResponse(
        HTTP_200=DeviceKeycloakStatusSchema,
        HTTP_404=ErrorResponseSchema,
        HTTP_502=ErrorResponseSchema,
    )
)
@handle_api_errors
@inject
def get_keycloak_status(
    device_id: int,
    device_service: DeviceService = Provide[ServiceContainer.device_service],
    metrics_service: MetricsService = Provide[ServiceContainer.metrics_service],
) -> Any:
    """Get Keycloak client status for a device.

    Returns whether the Keycloak client exists and provides a deep link
    to the Keycloak admin console. Does not return an error if the
    client is missing - instead returns exists=false.
    """
    start_time = time.perf_counter()
    status = "success"

    try:
        result = device_service.get_keycloak_status(device_id)
        return DeviceKeycloakStatusSchema.model_validate(result).model_dump()

    except Exception:
        status = "error"
        raise

    finally:
        duration = time.perf_counter() - start_time
        metrics_service.record_operation("get_keycloak_status", status, duration)


@devices_bp.route("/<int:device_id>/keycloak-sync", methods=["POST"])
@api.validate(
    resp=SpectreeResponse(
        HTTP_200=DeviceKeycloakStatusSchema,
        HTTP_404=ErrorResponseSchema,
        HTTP_502=ErrorResponseSchema,
    )
)
@handle_api_errors
@inject
def sync_keycloak_client(
    device_id: int,
    device_service: DeviceService = Provide[ServiceContainer.device_service],
    metrics_service: MetricsService = Provide[ServiceContainer.metrics_service],
) -> Any:
    """Create Keycloak client for a device if missing.

    Idempotent operation - if the client already exists, returns
    current status without making changes.
    """
    start_time = time.perf_counter()
    status = "success"

    try:
        result = device_service.sync_keycloak_client(device_id)
        return DeviceKeycloakStatusSchema.model_validate(result).model_dump()

    except Exception:
        status = "error"
        raise

    finally:
        duration = time.perf_counter() - start_time
        metrics_service.record_operation("sync_keycloak_client", status, duration)
