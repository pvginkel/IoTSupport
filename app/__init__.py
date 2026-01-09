"""Flask application factory for IoT Support backend."""

import logging
from typing import TYPE_CHECKING

from flask_cors import CORS

if TYPE_CHECKING:
    from app.config import Settings

from app.app import App
from app.config import get_settings
from app.services.container import ServiceContainer


def create_app(settings: "Settings | None" = None) -> App:
    """Create and configure Flask application."""
    app = App(__name__)

    # Load configuration
    if settings is None:
        settings = get_settings()

    app.config.from_object(settings)

    # Initialize SpecTree for OpenAPI docs
    from app.utils.spectree_config import configure_spectree

    configure_spectree(app)

    # Initialize service container
    container = ServiceContainer()
    container.config.override(settings)

    # Wire container with API modules
    wire_modules = [
        "app.api.configs",
        "app.api.health",
        "app.api.metrics",
    ]

    container.wire(modules=wire_modules)

    app.container = container

    # Configure CORS
    CORS(app, origins=settings.CORS_ORIGINS)

    # Configure logging
    logging.basicConfig(
        level=logging.DEBUG if settings.DEBUG else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Register main API blueprint
    from app.api import api_bp

    app.register_blueprint(api_bp)

    # Register metrics blueprint (at root, not under /api)
    from app.api.metrics import metrics_bp

    app.register_blueprint(metrics_bp)

    return app
