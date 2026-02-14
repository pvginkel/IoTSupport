"""App-specific startup hooks.

Hook points called by create_app():
  - create_container()
  - register_blueprints()
  - register_error_handlers()

Hook points called by CLI command handlers:
  - register_cli_commands()
  - post_migration_hook()
  - load_test_data_hook()
"""

from __future__ import annotations

import logging
import sys

import click
from flask import Blueprint, Flask

from app.services.container import ServiceContainer

logger = logging.getLogger(__name__)


def create_container() -> ServiceContainer:
    """Create and configure the application's service container."""
    return ServiceContainer()


def register_blueprints(api_bp: Blueprint, app: Flask) -> None:
    """Register all app-specific blueprints on api_bp (under /api prefix).

    Flask does not allow modifying a blueprint after its first registration,
    so child blueprints on api_bp are only registered once. Guard against
    repeated create_app() calls in test suites where api_bp is a module-level
    singleton.
    """
    if not api_bp._got_registered_once:  # type: ignore[attr-defined]
        from app.api.coredumps import coredumps_bp
        from app.api.device_models import device_models_bp
        from app.api.devices import devices_bp
        from app.api.images import images_bp
        from app.api.iot import iot_bp
        from app.api.pipeline import pipeline_bp
        from app.api.rotation import rotation_bp
        from app.api.testing import testing_bp

        api_bp.register_blueprint(coredumps_bp)  # type: ignore[attr-defined]
        api_bp.register_blueprint(device_models_bp)  # type: ignore[attr-defined]
        api_bp.register_blueprint(devices_bp)  # type: ignore[attr-defined]
        api_bp.register_blueprint(images_bp)  # type: ignore[attr-defined]
        api_bp.register_blueprint(iot_bp)  # type: ignore[attr-defined]
        api_bp.register_blueprint(pipeline_bp)  # type: ignore[attr-defined]
        api_bp.register_blueprint(rotation_bp)  # type: ignore[attr-defined]
        api_bp.register_blueprint(testing_bp)  # type: ignore[attr-defined]

    # CoredumpService needs a container reference for background-thread DB access.
    # This cannot be done via constructor injection because providers.Self()
    # resolves to None during Singleton construction.
    container = app.container
    container.coredump_service().container = container

    # Initialize LogSinkService singleton so it registers with the lifecycle
    # coordinator for MQTT subscription on startup.
    container.logsink_service()


def register_error_handlers(app: Flask) -> None:
    """Register app-specific error handlers for IoT exceptions."""
    from app.exceptions import (
        ExternalServiceException,
        ProcessingException,
        RecordExistsException,
        ServiceUnavailableException,
    )
    from app.utils.flask_error_handlers import (
        _mark_request_failed,
        build_error_response,
    )

    @app.errorhandler(RecordExistsException)
    def handle_record_exists(error: RecordExistsException) -> tuple:
        _mark_request_failed()
        logger.warning("Record exists: %s", error.message)
        return build_error_response(
            error.message,
            {"message": "The resource already exists"},
            code=error.error_code,
            status_code=409,
        )

    @app.errorhandler(ExternalServiceException)
    def handle_external_service(error: ExternalServiceException) -> tuple:
        _mark_request_failed()
        logger.warning("External service error: %s", error.message)
        return build_error_response(
            error.message,
            {"message": "External service request failed"},
            code=error.error_code,
            status_code=502,
        )

    @app.errorhandler(ServiceUnavailableException)
    def handle_service_unavailable(error: ServiceUnavailableException) -> tuple:
        _mark_request_failed()
        logger.warning("Service unavailable: %s", error.message)
        return build_error_response(
            error.message,
            {"message": "Service is temporarily unavailable"},
            code=error.error_code,
            status_code=503,
        )

    @app.errorhandler(ProcessingException)
    def handle_processing(error: ProcessingException) -> tuple:
        _mark_request_failed()
        logger.warning("Processing error: %s", error.message)
        return build_error_response(
            error.message,
            {"message": "Processing operation failed"},
            code=error.error_code,
            status_code=500,
        )


def register_cli_commands(cli: click.Group) -> None:
    """Register app-specific CLI commands."""
    from datetime import datetime

    from app.database import (
        check_db_connection,
        get_current_revision,
        get_pending_migrations,
    )

    @cli.command()
    @click.pass_context
    def db_status(ctx: click.Context) -> None:
        """Show database migration status."""
        app = ctx.obj["app"]
        with app.app_context():
            if not check_db_connection():
                print("Error: Cannot connect to database", file=sys.stderr)
                sys.exit(1)

            current = get_current_revision()
            pending = get_pending_migrations()

            if current:
                print(f"Current revision: {current}")
            else:
                print("No migrations applied yet")

            if pending:
                print(f"Pending migrations: {len(pending)}")
                for rev in pending:
                    print(f"  - {rev}")
            else:
                print("No pending migrations")

    # Setting key for last scheduled rotation timestamp
    LAST_SCHEDULED_AT_KEY = "LAST_SCHEDULED_AT"

    @cli.command()
    @click.pass_context
    def rotation_job(ctx: click.Context) -> None:
        """Execute rotation job for device credential rotation.

        Designed to be called by a Kubernetes CronJob. Performs a single
        rotation cycle: checks schedule, processes timeouts, rotates one device.
        """
        app = ctx.obj["app"]
        with app.app_context():
            if not check_db_connection():
                print("Error: Cannot connect to database", file=sys.stderr)
                sys.exit(1)

            settings_service = app.container.settings_service()
            last_scheduled_at = None

            last_scheduled_str = settings_service.get(LAST_SCHEDULED_AT_KEY)
            if last_scheduled_str:
                try:
                    last_scheduled_at = datetime.fromisoformat(last_scheduled_str)
                except ValueError as e:
                    print(f"Warning: Invalid last_scheduled_at value: {e}")

            try:
                rotation_service = app.container.rotation_service()
                result = rotation_service.process_rotation_job(last_scheduled_at)

                if result.scheduled_rotation_triggered:
                    settings_service.set(
                        LAST_SCHEDULED_AT_KEY, datetime.utcnow().isoformat()
                    )

                session = app.container.db_session()
                session.commit()

                print("Rotation job completed")
                print(f"  Timeouts processed: {result.processed_timeouts}")
                print(f"  Device rotated: {result.device_rotated or 'none'}")
                print(f"  Scheduled triggered: {result.scheduled_rotation_triggered}")

            except Exception as e:
                print(f"Error during rotation job: {e}", file=sys.stderr)
                sys.exit(1)


def post_migration_hook(app: Flask) -> None:
    """Run after database migrations (e.g., sync master data)."""
    pass


def load_test_data_hook(app: Flask) -> None:
    """Load test fixtures after database recreation."""
    print("Loading fixed test dataset...")
    test_data_service = app.container.test_data_service()
    counts = test_data_service.load_all()

    session = app.container.db_session()
    session.commit()

    print("Test data loaded successfully")
    print("Dataset summary:")
    for entity, count in counts.items():
        print(f"   - {count} {entity}")
