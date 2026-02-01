"""Health check endpoints for Kubernetes probes."""

from typing import Any

from dependency_injector.wiring import Provide, inject
from flask import Blueprint, jsonify

from app.database import check_db_connection
from app.services.container import ServiceContainer
from app.services.mqtt_service import MqttService
from app.utils.auth import public

health_bp = Blueprint("health", __name__, url_prefix="/health")


@health_bp.route("", methods=["GET"])
@public
@inject
def health_check(
    mqtt_service: MqttService = Provide[ServiceContainer.mqtt_service],
) -> Any:
    """Health check endpoint for Kubernetes probes.

    Returns 200 when database and MQTT are accessible.
    Returns 503 when database or MQTT is not accessible.
    """
    db_connected = check_db_connection()
    mqtt_connected = mqtt_service.enabled

    is_healthy = db_connected and mqtt_connected

    response = {
        "status": "healthy" if is_healthy else "unhealthy",
        "database": "connected" if db_connected else "disconnected",
        "mqtt": "connected" if mqtt_connected else "disconnected",
    }

    if not is_healthy:
        errors = []
        if not db_connected:
            errors.append("database not connected")
        if not mqtt_connected:
            errors.append("MQTT not connected")
        response["error"] = ", ".join(errors)

    return jsonify(response), 200 if is_healthy else 503
