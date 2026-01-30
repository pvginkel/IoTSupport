"""Flask application factory for IoT Support backend."""

import logging
from typing import TYPE_CHECKING

from flask_cors import CORS

if TYPE_CHECKING:
    from app.config import Settings

from app.app import App
from app.config import Settings
from app.extensions import db
from app.services.container import ServiceContainer


def create_app(settings: "Settings | None" = None, skip_background_services: bool = False) -> App:
    """Create and configure Flask application."""
    app = App(__name__)

    # Load configuration
    if settings is None:
        settings = Settings.load()

    # Validate production configuration
    settings.validate_production_config()

    app.config.from_object(settings.to_flask_config())

    # Initialize Flask-SQLAlchemy
    db.init_app(app)

    # Import models to register them with SQLAlchemy
    from app import models  # noqa: F401

    # Initialize SessionLocal for per-request sessions
    # This needs to be done in app context since db.engine requires it
    with app.app_context():
        from sqlalchemy.orm import Session, sessionmaker

        SessionLocal: sessionmaker[Session] = sessionmaker(
            class_=Session,
            bind=db.engine,
            autoflush=True,
            expire_on_commit=False,
        )

    # Initialize SpecTree for OpenAPI docs
    from app.utils.spectree_config import configure_spectree

    configure_spectree(app)

    # Initialize service container
    container = ServiceContainer()
    container.config.override(settings)
    container.session_maker.override(SessionLocal)

    # Wire container with API modules
    wire_modules = [
        "app.api",
        "app.api.auth",
        "app.api.device_models",
        "app.api.devices",
        "app.api.health",
        "app.api.images",
        "app.api.iot",
        "app.api.metrics",
        "app.api.pipeline",
        "app.api.rotation",
        "app.api.testing",
    ]

    container.wire(modules=wire_modules)

    app.container = container

    # Configure CORS
    CORS(app, origins=settings.cors_origins)

    # Configure logging
    debug_mode = settings.flask_env in ("development", "testing")
    logging.basicConfig(
        level=logging.DEBUG if debug_mode else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Register main API blueprint
    from app.api import api_bp

    app.register_blueprint(api_bp)

    # Register metrics blueprint (at root, not under /api)
    from app.api.metrics import metrics_bp

    app.register_blueprint(metrics_bp)


    # Request teardown handler for database session management
    @app.teardown_request
    def close_session(exc: Exception | None) -> None:
        """Close the database session after each request."""
        try:
            db_session = container.db_session()
            needs_rollback = db_session.info.get("needs_rollback", False)

            if exc or needs_rollback:
                db_session.rollback()
            else:
                db_session.commit()

            # Clear rollback flag after processing
            db_session.info.pop("needs_rollback", None)
            db_session.close()

        finally:
            # Ensure the scoped session is removed after each request
            container.db_session.reset()

    return app
