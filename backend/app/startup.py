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
import httpx
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
        from app.api.device_log_stream import device_log_stream_bp
        from app.api.device_models import device_models_bp
        from app.api.devices import devices_bp
        from app.api.images import images_bp
        from app.api.iot import iot_bp
        from app.api.pipeline import pipeline_bp
        from app.api.rotation import rotation_bp
        from app.api.testing import testing_bp

        api_bp.register_blueprint(coredumps_bp)  # type: ignore[attr-defined]
        api_bp.register_blueprint(device_log_stream_bp)  # type: ignore[attr-defined]
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


def _notify_rotation_nudge(app: Flask) -> None:
    """POST to the web process's internal endpoint to trigger a rotation nudge broadcast.

    Best-effort: failures are logged but do not fail the rotation job.
    No-op if INTERNAL_API_URL is not configured.
    """
    app_config = app.container.app_config()
    internal_url = app_config.internal_api_url

    if not internal_url:
        logger.debug("INTERNAL_API_URL not configured, skipping rotation nudge notification")
        return

    url = f"{internal_url}/internal/rotation-nudge"
    try:
        response = httpx.post(url, json={}, timeout=5.0)
        response.raise_for_status()
        logger.info("Rotation nudge notification sent to web process")
    except Exception as e:
        # Best-effort: log and continue. The next CronJob tick will trigger
        # another nudge anyway.
        logger.warning("Failed to send rotation nudge notification: %s", e)


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
        After processing, notifies the web process to broadcast a rotation
        nudge via the internal API endpoint (best-effort).
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

                # Notify web process to broadcast rotation nudge (best-effort).
                # The CronJob runs in a separate process without SSE connections,
                # so it delegates the broadcast to the web process via HTTP.
                _notify_rotation_nudge(app)

            except Exception as e:
                print(f"Error during rotation job: {e}", file=sys.stderr)
                sys.exit(1)


    @cli.command()
    @click.option("--dry-run", is_flag=True, help="List files that would be migrated without uploading")
    @click.pass_context
    def migrate_to_s3(ctx: click.Context, dry_run: bool) -> None:
        """Migrate firmware and coredump files from filesystem to S3.

        One-time migration command for transitioning from ASSETS_DIR/COREDUMPS_DIR
        filesystem storage to S3. Reads legacy paths from ASSETS_DIR and COREDUMPS_DIR
        environment variables.

        Firmware ZIPs are extracted and individual artifacts are uploaded to S3
        under firmware/{model_code}/{version}/. Coredump .dmp files are uploaded
        to S3 under coredumps/{device_key}/{db_id}.dmp.

        This command is idempotent: re-running it re-uploads files that may
        already exist in S3 (S3 PUT is inherently idempotent).
        """
        from app.services.migration_service import MigrationService

        app = ctx.obj["app"]
        with app.app_context():
            if not check_db_connection():
                print("Error: Cannot connect to database", file=sys.stderr)
                sys.exit(1)

            # Verify S3 connectivity
            try:
                s3_service = app.container.s3_service()
                s3_service.ensure_bucket_exists()
            except Exception as e:
                print(f"Error: S3 is not reachable: {e}", file=sys.stderr)
                sys.exit(1)

            app_settings = app.container.app_config()
            session = app.container.db_session()

            migration = MigrationService(
                s3_service=s3_service,
                db=session,
                assets_dir=app_settings.assets_dir,
                coredumps_dir=app_settings.coredumps_dir,
                dry_run=dry_run,
            )

            try:
                summary = migration.run()
                session.commit()
            except Exception as e:
                session.rollback()
                print(f"Error: Migration failed: {e}", file=sys.stderr)
                sys.exit(1)

            # Print summary
            mode = "[DRY RUN] " if dry_run else ""
            print(f"\n{mode}Migration complete.")
            print(f"  Firmware ZIPs migrated: {summary['firmware_zips']}")
            print(f"  Firmware ZIPs skipped:  {summary['firmware_skipped']}")
            print(f"  Coredumps migrated:     {summary['coredumps_migrated']}")
            print(f"  Coredumps skipped:      {summary['coredumps_skipped']}")

            if summary.get("warnings"):
                print(f"\n  Warnings ({len(summary['warnings'])}):")
                for warning in summary["warnings"]:
                    print(f"    - {warning}")


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
