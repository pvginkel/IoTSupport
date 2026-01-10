"""API blueprints for IoT Support Backend."""

from flask import Blueprint

# Create main API blueprint
api_bp = Blueprint("api", __name__, url_prefix="/api")


# Import and register all resource blueprints
# Note: Imports are done after api_bp creation to avoid circular imports
from app.api.assets import assets_bp  # noqa: E402
from app.api.configs import configs_bp  # noqa: E402
from app.api.health import health_bp  # noqa: E402

api_bp.register_blueprint(assets_bp)  # type: ignore[attr-defined]
api_bp.register_blueprint(configs_bp)  # type: ignore[attr-defined]
api_bp.register_blueprint(health_bp)  # type: ignore[attr-defined]
