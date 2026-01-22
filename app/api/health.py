"""Health check endpoints for Kubernetes probes."""

from typing import Any

from flask import Blueprint, jsonify

from app.database import check_db_connection
from app.utils.auth import public

health_bp = Blueprint("health", __name__, url_prefix="/health")


@health_bp.route("", methods=["GET"])
@public
def health_check() -> Any:
    """Health check endpoint for Kubernetes probes.

    Returns 200 when database is accessible.
    Returns 503 when database is not accessible.
    """
    is_connected = check_db_connection()

    if is_connected:
        return jsonify({"status": "healthy", "database": "connected"}), 200
    else:
        return jsonify({
            "status": "unhealthy",
            "database": "disconnected",
            "error": "Failed to connect to database"
        }), 503
