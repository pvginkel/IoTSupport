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
@click.option(
    "--yes-i-am-sure",
    is_flag=True,
    help="Required safety flag when using --recreate",
)
def upgrade_db(recreate: bool, yes_i_am_sure: bool) -> None:
    """Upgrade database to latest migration.

    Applies all pending Alembic migrations to bring the database schema up to date.
    Use --recreate to drop all tables first (useful for development).

    Examples:
        iotsupport-cli upgrade-db                              Apply pending migrations
        iotsupport-cli upgrade-db --recreate --yes-i-am-sure   Drop all tables and recreate
    """
    # Safety check for recreate
    if recreate and not yes_i_am_sure:
        click.echo(
            "Error: --recreate requires --yes-i-am-sure flag for safety", err=True
        )
        click.echo(
            "   This will DROP ALL TABLES and recreate from migrations!", err=True
        )
        sys.exit(1)

    app = create_app(skip_background_services=True)

    with app.app_context():
        # Check database connection first
        if not check_db_connection():
            click.echo("Error: Cannot connect to database", err=True)
            sys.exit(1)

        # Let operator know which database is targeted
        click.echo(f"Using database: {app.config['SQLALCHEMY_DATABASE_URI']}")

        if recreate:
            click.echo("WARNING: About to drop all tables and recreate from migrations!")
            click.echo("   This will permanently delete all data in the database.")

        # Show pending migrations
        pending = get_pending_migrations()
        if not pending and not recreate:
            click.echo("Database is already up to date")
            return

        if pending:
            click.echo(f"Found {len(pending)} pending migration(s)")

        # Run upgrade
        try:
            if recreate:
                click.echo("Recreating database from scratch...")

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
@click.option(
    "--yes-i-am-sure",
    is_flag=True,
    help="Required safety flag to confirm database recreation",
)
def load_test_data(yes_i_am_sure: bool) -> None:
    """Recreate database and load fixed test data.

    This command:
    1. Drops all tables and recreates the database schema (like upgrade-db --recreate)
    2. Loads fixed test data from app/data/test_data/

    Examples:
        iotsupport-cli load-test-data --yes-i-am-sure    Load complete test dataset
    """
    # Safety check for confirmation
    if not yes_i_am_sure:
        click.echo("Error: --yes-i-am-sure flag is required for safety", err=True)
        click.echo(
            "   This will DROP ALL TABLES and recreate with test data!", err=True
        )
        sys.exit(1)

    app = create_app(skip_background_services=True)

    with app.app_context():
        # Check database connection first
        if not check_db_connection():
            click.echo("Error: Cannot connect to database", err=True)
            sys.exit(1)

        # Let operator know which database is targeted
        click.echo(f"Using database: {app.config['SQLALCHEMY_DATABASE_URI']}")
        click.echo("WARNING: About to drop all tables and load test data!")
        click.echo("   This will permanently delete all existing data in the database.")

        try:
            # First recreate the database
            click.echo("Recreating database from scratch...")
            applied = upgrade_database(recreate=True)

            if applied:
                click.echo(f"Database recreated with {len(applied)} migration(s)")
            else:
                click.echo("Database recreated successfully")

            # Load test data
            click.echo("Loading fixed test dataset...")
            test_data_service = app.container.test_data_service()
            count = test_data_service.load_configs()

            # Commit the loaded data
            session = app.container.db_session()
            session.commit()

            click.echo("Test data loaded successfully")
            click.echo("Dataset summary:")
            click.echo(f"   - {count} device configurations")

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
