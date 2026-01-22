"""Configuration management API endpoints."""

import time
from typing import Any

from dependency_injector.wiring import Provide, inject
from flask import Blueprint, request
from spectree import Response as SpectreeResponse

from app.schemas.config import (
    ConfigCreateRequestSchema,
    ConfigListResponseSchema,
    ConfigResponseSchema,
    ConfigSummarySchema,
    ConfigUpdateRequestSchema,
)
from app.schemas.error import ErrorResponseSchema
from app.services.config_service import ConfigService
from app.services.container import ServiceContainer
from app.services.metrics_service import MetricsService
from app.services.mqtt_service import MqttService
from app.utils.auth import public
from app.utils.error_handling import handle_api_errors
from app.utils.spectree_config import api

configs_bp = Blueprint("configs", __name__, url_prefix="/configs")


@configs_bp.route("", methods=["GET"])
@api.validate(resp=SpectreeResponse(HTTP_200=ConfigListResponseSchema))
@handle_api_errors
@inject
def list_configs(
    config_service: ConfigService = Provide[ServiceContainer.config_service],
    metrics_service: MetricsService = Provide[ServiceContainer.metrics_service],
) -> Any:
    """List all configurations with summary data."""
    start_time = time.perf_counter()
    status = "success"

    try:
        configs = config_service.list_configs()

        # Update metrics
        metrics_service.update_config_count(len(configs))

        # Convert to response schema
        config_summaries = [
            ConfigSummarySchema.model_validate(c)
            for c in configs
        ]

        return ConfigListResponseSchema(
            configs=config_summaries, count=len(configs)
        ).model_dump()

    except Exception:
        status = "error"
        raise

    finally:
        duration = time.perf_counter() - start_time
        metrics_service.record_operation("list", status, duration)


@configs_bp.route("", methods=["POST"])
@api.validate(
    json=ConfigCreateRequestSchema,
    resp=SpectreeResponse(
        HTTP_201=ConfigResponseSchema,
        HTTP_400=ErrorResponseSchema,
        HTTP_409=ErrorResponseSchema,
    ),
)
@handle_api_errors
@inject
def create_config(
    config_service: ConfigService = Provide[ServiceContainer.config_service],
    metrics_service: MetricsService = Provide[ServiceContainer.metrics_service],
    mqtt_service: MqttService = Provide[ServiceContainer.mqtt_service],
) -> Any:
    """Create a new configuration."""
    start_time = time.perf_counter()
    status = "success"

    try:
        data = ConfigCreateRequestSchema.model_validate(request.get_json())

        config = config_service.create_config(data.mac_address, data.content)

        # Update config count after create
        config_count = config_service.count_configs()
        metrics_service.update_config_count(config_count)

        # Publish MQTT notification after successful create
        mqtt_service.publish_config_update(f"{config.mac_address}.json")

        return ConfigResponseSchema.model_validate(config).model_dump(), 201

    except Exception:
        status = "error"
        raise

    finally:
        duration = time.perf_counter() - start_time
        metrics_service.record_operation("create", status, duration)


@configs_bp.route("/<mac_address>.json", methods=["GET"])
@public
@handle_api_errors
@inject
def get_config_raw(
    mac_address: str,
    config_service: ConfigService = Provide[ServiceContainer.config_service],
    metrics_service: MetricsService = Provide[ServiceContainer.metrics_service],
) -> Any:
    """Get raw JSON configuration for ESP32 device consumption.

    This endpoint returns the raw config content without wrapping,
    suitable for direct consumption by ESP32 devices.
    Accepts both colon-separated and dash-separated MAC formats.
    """
    start_time = time.perf_counter()
    status = "success"

    try:
        content = config_service.get_raw_config(mac_address)

        # Return raw content dict with Cache-Control header
        response = (content, 200, {"Cache-Control": "no-cache"})
        return response

    except Exception:
        status = "error"
        raise

    finally:
        duration = time.perf_counter() - start_time
        metrics_service.record_operation("get_raw", status, duration)


@configs_bp.route("/<int:config_id>", methods=["GET"])
@api.validate(
    resp=SpectreeResponse(HTTP_200=ConfigResponseSchema, HTTP_404=ErrorResponseSchema)
)
@handle_api_errors
@inject
def get_config(
    config_id: int,
    config_service: ConfigService = Provide[ServiceContainer.config_service],
    metrics_service: MetricsService = Provide[ServiceContainer.metrics_service],
) -> Any:
    """Get single configuration by ID."""
    start_time = time.perf_counter()
    status = "success"

    try:
        config = config_service.get_config_by_id(config_id)

        return ConfigResponseSchema.model_validate(config).model_dump()

    except Exception:
        status = "error"
        raise

    finally:
        duration = time.perf_counter() - start_time
        metrics_service.record_operation("get", status, duration)


@configs_bp.route("/<int:config_id>", methods=["PUT"])
@api.validate(
    json=ConfigUpdateRequestSchema,
    resp=SpectreeResponse(
        HTTP_200=ConfigResponseSchema,
        HTTP_400=ErrorResponseSchema,
        HTTP_404=ErrorResponseSchema,
    ),
)
@handle_api_errors
@inject
def update_config(
    config_id: int,
    config_service: ConfigService = Provide[ServiceContainer.config_service],
    metrics_service: MetricsService = Provide[ServiceContainer.metrics_service],
    mqtt_service: MqttService = Provide[ServiceContainer.mqtt_service],
) -> Any:
    """Update configuration by ID."""
    start_time = time.perf_counter()
    status = "success"

    try:
        data = ConfigUpdateRequestSchema.model_validate(request.get_json())

        config = config_service.update_config(config_id, data.content)

        # Publish MQTT notification after successful update
        mqtt_service.publish_config_update(f"{config.mac_address}.json")

        return ConfigResponseSchema.model_validate(config).model_dump()

    except Exception:
        status = "error"
        raise

    finally:
        duration = time.perf_counter() - start_time
        metrics_service.record_operation("update", status, duration)


@configs_bp.route("/<int:config_id>", methods=["DELETE"])
@api.validate(
    resp=SpectreeResponse(HTTP_204=None, HTTP_404=ErrorResponseSchema)
)
@handle_api_errors
@inject
def delete_config(
    config_id: int,
    config_service: ConfigService = Provide[ServiceContainer.config_service],
    metrics_service: MetricsService = Provide[ServiceContainer.metrics_service],
) -> Any:
    """Delete configuration by ID."""
    start_time = time.perf_counter()
    status = "success"

    try:
        config_service.delete_config(config_id)

        # Update config count after delete
        config_count = config_service.count_configs()
        metrics_service.update_config_count(config_count)

        return "", 204

    except Exception:
        status = "error"
        raise

    finally:
        duration = time.perf_counter() - start_time
        metrics_service.record_operation("delete", status, duration)
