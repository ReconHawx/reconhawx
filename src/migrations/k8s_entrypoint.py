"""
Kubernetes API Deployment init container entrypoint.

1. Build DATABASE_URL from POSTGRES_* env vars if DATABASE_URL is unset.
2. Hybrid baseline snapshot: if the database already matches the bundled pg_dump
   (fresh install) or was migrated by the legacy SQL tracker, stamp Alembic at head.
3. Run ``alembic upgrade head`` so any new revisions apply on upgrades.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import psycopg2
from alembic import command
from alembic.config import Config

logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


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


def get_database_url() -> str:
    ensure_database_url()
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    return url


def _alembic_config() -> Config:
    ini = Path(__file__).resolve().parent / "alembic.ini"
    cfg = Config(str(ini))
    cfg.set_main_option("sqlalchemy.url", get_database_url())
    return cfg


def _alembic_has_revision(cur) -> bool:
    cur.execute(
        """
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'alembic_version'
        )
        """
    )
    if not cur.fetchone()[0]:
        return False
    cur.execute("SELECT version_num FROM alembic_version LIMIT 1")
    return cur.fetchone() is not None


def _legacy_schema_migrations_has_success(cur) -> bool:
    cur.execute(
        """
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'schema_migrations'
        )
        """
    )
    if not cur.fetchone()[0]:
        return False
    cur.execute(
        "SELECT 1 FROM schema_migrations WHERE success = true LIMIT 1"
    )
    return cur.fetchone() is not None


def _users_table_exists(cur) -> bool:
    cur.execute(
        """
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'users'
        )
        """
    )
    return cur.fetchone()[0]


def _should_stamp_head(cur) -> bool:
    if _alembic_has_revision(cur):
        return False
    if _legacy_schema_migrations_has_success(cur):
        logger.info("Legacy schema_migrations detected; will stamp Alembic head")
        return True
    if _users_table_exists(cur):
        logger.info(
            "Application schema present without Alembic revision; "
            "assuming fresh install from schema.sql — stamping head"
        )
        return True
    logger.info(
        "Empty or non-standard database: skipping stamp; migrations will run from base"
    )
    return False


def main() -> None:
    setup_logging(verbose=os.getenv("MIGRATIONS_VERBOSE") == "1")
    ensure_database_url()
    db_url = get_database_url()

    stamp = False
    with psycopg2.connect(db_url) as conn:
        with conn.cursor() as cur:
            stamp = _should_stamp_head(cur)
    if stamp:
        logger.info("Running: alembic stamp head")
        command.stamp(_alembic_config(), "head")

    logger.info("Running: alembic upgrade head")
    command.upgrade(_alembic_config(), "head")
    logger.info("Migrations complete")


if __name__ == "__main__":
    main()
