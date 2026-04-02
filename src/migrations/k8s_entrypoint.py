"""
Kubernetes API Deployment init container entrypoint.

1. Build DATABASE_URL from POSTGRES_* env vars if DATABASE_URL is unset.
2. Optional: If MIGRATIONS_BASELINE_AUTOMARK is enabled, and the DB looks like a fresh
   install from postgresql/schema.sql (app tables exist, schema_migrations empty, pending
   SQL files present), mark those files applied without executing SQL. **Default is off**
   so real migrations always run; enable only for bookkeeping-only files that mirror
   the bundled dump.
3. Run pending migrations.
"""

from __future__ import annotations

import logging
import os
import sys
import psycopg2

from migrations.cli import get_db_url, get_migrations_dir, setup_logging
from migrations.migration_manager import MigrationManager
from migrations.migration_runner import MigrationRunner

logger = logging.getLogger(__name__)


def ensure_database_url() -> None:
    """Set DATABASE_URL from discrete env vars when not provided (Kube-friendly)."""
    if os.getenv("DATABASE_URL"):
        return

    from urllib.parse import quote_plus

    user = os.environ["POSTGRES_USER"]
    password = os.environ["POSTGRES_PASSWORD"]
    dbname = os.environ.get("DATABASE_NAME", "reconhawx")
    host = os.environ.get("POSTGRES_HOST", "postgresql")
    port = os.environ.get("POSTGRES_PORT", "5432")
    os.environ["DATABASE_URL"] = (
        f"postgresql://{quote_plus(user)}:{quote_plus(password)}@{host}:{port}/{dbname}"
    )


def _bootstrap_migration_manager(db_url: str, migrations_dir: str) -> MigrationManager:
    """Create MigrationManager (ensures schema_migrations table exists)."""
    return MigrationManager(migrations_dir, db_url)


def _schema_migrations_total_rows(manager: MigrationManager) -> int:
    table = manager.migrations_table
    with psycopg2.connect(manager.db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            row = cur.fetchone()
            return int(row[0]) if row else 0


def _baseline_automark_enabled() -> bool:
    """True when operator opts in (e.g. migration files only track baseline dump, no DDL)."""
    v = (os.getenv("MIGRATIONS_BASELINE_AUTOMARK") or "").strip().lower()
    return v in ("1", "true", "yes")


def _public_app_table_count(db_url: str) -> int:
    """Count user tables in public, excluding migration bookkeeping."""
    with psycopg2.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_type = 'BASE TABLE'
                  AND table_name NOT IN ('schema_migrations')
                """
            )
            row = cur.fetchone()
            return int(row[0]) if row else 0


def maybe_mark_baseline_migrations_applied() -> None:
    """
    Baseline from schema.sql: many tables exist, schema_migrations is still empty,
    and we ship one or more V*.sql files. Mark those files applied without executing.

    **Only runs when MIGRATIONS_BASELINE_AUTOMARK is set** — otherwise every pending
    file is executed, which is required for real DDL after the bundled dump.

    Skip if schema_migrations already has any row (success or failure) so we never
    auto-mark over a partially migrated DB.
    """
    if not _baseline_automark_enabled():
        logger.info(
            "MIGRATIONS_BASELINE_AUTOMARK not enabled; skipping mark-as-applied for dump baseline"
        )
        return

    db_url = get_db_url()
    migrations_dir = get_migrations_dir()
    manager = _bootstrap_migration_manager(db_url, migrations_dir)

    if _schema_migrations_total_rows(manager) > 0:
        logger.info("schema_migrations non-empty; skipping baseline mark-as-applied")
        return

    pending = manager.get_pending_migrations()
    if not pending:
        logger.info("No pending migration SQL files")
        return

    app_tables = _public_app_table_count(db_url)
    if app_tables == 0:
        logger.info("No application tables yet; will run SQL migrations normally")
        return

    logger.info(
        "Baseline schema detected (%d app tables, %d pending version file(s)); "
        "marking migration files as applied without executing SQL",
        app_tables,
        len(pending),
    )
    for migration in pending:
        manager.record_migration(
            migration,
            success=True,
            execution_time_ms=0,
            error_message=None,
        )


def main() -> None:
    setup_logging(verbose=os.getenv("MIGRATIONS_VERBOSE") == "1")
    ensure_database_url()
    maybe_mark_baseline_migrations_applied()

    runner = MigrationRunner(get_db_url(), get_migrations_dir())
    result = runner.run_migrations(dry_run=False)

    if result["success"]:
        logger.info("Migrations complete (applied this run: %s)", result.get("migrations_run", 0))
        return

    for err in result.get("errors", []):
        logger.error("%s", err)
    sys.exit(1)


if __name__ == "__main__":
    main()
