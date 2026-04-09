"""
Alembic environment configuration.

Runtime (K8s init container): target_metadata may be None; upgrade/stamp still work.

Local autogenerate: ensure PYTHONPATH includes repo src/ and src/api/app (see scripts/migrate.sh).
"""
from __future__ import annotations

import logging
import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

logger = logging.getLogger("alembic.env")

# --- SQLAlchemy metadata (optional: Docker image ships without full API tree) ---
_target_metadata = None
try:
    _here = Path(__file__).resolve()
    _repo_root = _here.parents[3]  # .../src/migrations/alembic/env.py -> repo root
    _api_app = _repo_root / "src" / "api" / "app"
    if _api_app.is_dir():
        sys.path.insert(0, str(_api_app))
    from models.postgres import Base  # noqa: E402
    import models.refresh_token  # noqa: E402, F401  # registers RefreshToken on Base.metadata

    _target_metadata = Base.metadata
except Exception as exc:  # pragma: no cover - image path
    logger.warning("Could not import ORM models for autogenerate metadata: %s", exc)

target_metadata = _target_metadata

# Tables managed only via SQL / not in ORM — never autogenerate DROP for these
_SKIP_AUTOGEN_NAMES = frozenset(
    {"action_logs", "droopescan_findings", "schema_migrations", "alembic_version"}
)


def include_object(object_, name, type_, reflected, compare_to):  # noqa: ARG001
    if type_ == "table" and name in _SKIP_AUTOGEN_NAMES:
        return False
    return True


def _get_url() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if url:
        return url
    from urllib.parse import quote_plus

    user = os.environ["POSTGRES_USER"]
    password = os.environ["POSTGRES_PASSWORD"]
    dbname = os.environ.get("DATABASE_NAME", "reconhawx")
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    return (
        f"postgresql://{quote_plus(user)}:{quote_plus(password)}@{host}:{port}/{dbname}"
    )


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)
config.set_main_option("sqlalchemy.url", _get_url())


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL to stdout)."""
    context.configure(
        url=_get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (engine connection)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
