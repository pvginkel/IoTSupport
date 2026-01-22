"""CLI entry point for IoT Support backend management commands."""

import sys

import click

from app import create_app
from app.database import check_db_connection, get_pending_migrations, upgrade_database


@click.group()
def cli() -> None:
    """IoT Support CLI - Database and application management commands."""
    pass


@cli.command()
@click.option("--recreate", is_flag=True, help="Drop all tables before upgrading")
def upgrade_db(recreate: bool) -> None:
    """Upgrade database to latest migration.

    Applies all pending Alembic migrations to bring the database schema up to date.
    Use --recreate to drop all tables first (useful for development).
    """
    app = create_app(skip_background_services=True)

    with app.app_context():
        # Check database connection first
        if not check_db_connection():
            click.echo("Error: Cannot connect to database", err=True)
            sys.exit(1)

        # Show pending migrations
        pending = get_pending_migrations()
        if not pending and not recreate:
            click.echo("Database is already up to date")
            return

        if pending:
            click.echo(f"Found {len(pending)} pending migration(s)")

        # Run upgrade
        try:
            applied = upgrade_database(recreate=recreate)
            if applied:
                click.echo(f"Applied {len(applied)} migration(s):")
                for rev, desc in applied:
                    click.echo(f"  - {rev}: {desc}")
            click.echo("Database upgrade complete")
        except Exception as e:
            click.echo(f"Error during database upgrade: {e}", err=True)
            sys.exit(1)


@cli.command()
def load_test_data() -> None:
    """Load test data into the database.

    Loads sample configuration data from app/data/test_data/configs.json.
    """
    app = create_app(skip_background_services=True)

    with app.app_context():
        # Check database connection first
        if not check_db_connection():
            click.echo("Error: Cannot connect to database", err=True)
            sys.exit(1)

        try:
            test_data_service = app.container.test_data_service()
            count = test_data_service.load_configs()
            click.echo(f"Loaded {count} configuration(s)")
        except Exception as e:
            click.echo(f"Error loading test data: {e}", err=True)
            sys.exit(1)


@cli.command()
def db_status() -> None:
    """Show database migration status.

    Displays current database revision and any pending migrations.
    """
    app = create_app(skip_background_services=True)

    with app.app_context():
        # Check database connection first
        if not check_db_connection():
            click.echo("Error: Cannot connect to database", err=True)
            sys.exit(1)

        from app.database import get_current_revision

        current = get_current_revision()
        pending = get_pending_migrations()

        if current:
            click.echo(f"Current revision: {current}")
        else:
            click.echo("No migrations applied yet")

        if pending:
            click.echo(f"Pending migrations: {len(pending)}")
            for rev in pending:
                click.echo(f"  - {rev}")
        else:
            click.echo("No pending migrations")


def main() -> None:
    """Entry point for CLI."""
    cli()


if __name__ == "__main__":
    main()
