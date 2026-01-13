"""Configuration management API endpoints."""

import time
from typing import Any

from dependency_injector.wiring import Provide, inject
from flask import Blueprint, request
from spectree import Response as SpectreeResponse

from app.schemas.config import (
    ConfigListResponseSchema,
    ConfigResponseSchema,
    ConfigSaveRequestSchema,
    ConfigSummarySchema,
)
from app.schemas.error import ErrorResponseSchema
from app.services.config_service import ConfigService
from app.services.container import ServiceContainer
from app.services.metrics_service import MetricsService
from app.services.mqtt_service import MqttService
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
            ConfigSummarySchema(
                mac_address=c.mac_address,
                device_name=c.device_name,
                device_entity_id=c.device_entity_id,
                enable_ota=c.enable_ota,
            )
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


@configs_bp.route("/<mac_address>", methods=["GET"])
@api.validate(
    resp=SpectreeResponse(HTTP_200=ConfigResponseSchema, HTTP_400=ErrorResponseSchema, HTTP_404=ErrorResponseSchema)
)
@handle_api_errors
@inject
def get_config(
    mac_address: str,
    config_service: ConfigService = Provide[ServiceContainer.config_service],
    metrics_service: MetricsService = Provide[ServiceContainer.metrics_service],
) -> Any:
    """Get single configuration by MAC address."""
    start_time = time.perf_counter()
    status = "success"

    try:
        config = config_service.get_config(mac_address)

        return ConfigResponseSchema(
            mac_address=config.mac_address,
            device_name=config.device_name,
            device_entity_id=config.device_entity_id,
            enable_ota=config.enable_ota,
            content=config.content,
        ).model_dump()

    except Exception:
        status = "error"
        raise

    finally:
        duration = time.perf_counter() - start_time
        metrics_service.record_operation("get", status, duration)


@configs_bp.route("/<mac_address>", methods=["PUT"])
@api.validate(
    json=ConfigSaveRequestSchema,
    resp=SpectreeResponse(
        HTTP_200=ConfigResponseSchema,
        HTTP_400=ErrorResponseSchema,
        HTTP_409=ErrorResponseSchema,
    ),
)
@handle_api_errors
@inject
def save_config(
    mac_address: str,
    config_service: ConfigService = Provide[ServiceContainer.config_service],
    metrics_service: MetricsService = Provide[ServiceContainer.metrics_service],
    mqtt_service: MqttService = Provide[ServiceContainer.mqtt_service],
) -> Any:
    """Create or update configuration (upsert)."""
    start_time = time.perf_counter()
    status = "success"

    try:
        # Spectree validates the request, but we still need to access the data
        data = ConfigSaveRequestSchema.model_validate(request.get_json())

        config = config_service.save_config(
            mac_address, data.content, allow_overwrite=data.allow_overwrite
        )

        # Update config count after save
        configs = config_service.list_configs()
        metrics_service.update_config_count(len(configs))

        # Publish MQTT notification after successful save and metrics update
        mqtt_service.publish_config_update(f"{mac_address}.json")

        return ConfigResponseSchema(
            mac_address=config.mac_address,
            device_name=config.device_name,
            device_entity_id=config.device_entity_id,
            enable_ota=config.enable_ota,
            content=config.content,
        ).model_dump()

    except Exception:
        status = "error"
        raise

    finally:
        duration = time.perf_counter() - start_time
        metrics_service.record_operation("save", status, duration)


@configs_bp.route("/<mac_address>", methods=["DELETE"])
@api.validate(
    resp=SpectreeResponse(HTTP_204=None, HTTP_400=ErrorResponseSchema, HTTP_404=ErrorResponseSchema)
)
@handle_api_errors
@inject
def delete_config(
    mac_address: str,
    config_service: ConfigService = Provide[ServiceContainer.config_service],
    metrics_service: MetricsService = Provide[ServiceContainer.metrics_service],
) -> Any:
    """Delete configuration by MAC address."""
    start_time = time.perf_counter()
    status = "success"

    try:
        config_service.delete_config(mac_address)

        # Update config count after delete
        configs = config_service.list_configs()
        metrics_service.update_config_count(len(configs))

        return "", 204

    except Exception:
        status = "error"
        raise

    finally:
        duration = time.perf_counter() - start_time
        metrics_service.record_operation("delete", status, duration)
