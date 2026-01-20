"""Health check endpoints for Kubernetes probes."""

from typing import Any

from dependency_injector.wiring import Provide, inject
from flask import Blueprint, jsonify

from app.services.config_service import ConfigService
from app.services.container import ServiceContainer
from app.utils.auth import public

health_bp = Blueprint("health", __name__, url_prefix="/health")


@health_bp.route("", methods=["GET"])
@public
@inject
def health_check(
    config_service: ConfigService = Provide[ServiceContainer.config_service],
) -> Any:
    """Health check endpoint for Kubernetes probes.

    Returns 200 when config directory is accessible.
    Returns 503 when config directory is not accessible.
    """
    is_accessible, error_reason = config_service.is_config_dir_accessible()

    if is_accessible:
        return jsonify({"status": "healthy"}), 200
    else:
        return jsonify({"status": "unhealthy", "reason": error_reason}), 503
