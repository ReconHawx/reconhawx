"""
Optional Postgres check: migration_0013_lower_url_host(plpgsql) vs Python lower_url_host().

Requires DATABASE_URL pointing at Postgres and RECON_PG_MIGRATION_SMOKE=1.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from app.utils.url_utils import lower_url_host


pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL must point at Postgres for migration function smoke tests",
)


REPO_ROOT = Path(__file__).resolve().parents[3]
_MIGRATION_FILE = REPO_ROOT / "src" / "migrations" / "alembic" / "versions" / "0013_lowercase_hostnames.py"


def _load_migration_module():
    spec = importlib.util.spec_from_file_location("migration_0013_lowercase_hostnames", _MIGRATION_FILE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {_MIGRATION_FILE}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.skipif(
    os.environ.get("RECON_PG_MIGRATION_SMOKE", "").lower() not in {"1", "true", "yes"},
    reason="Set RECON_PG_MIGRATION_SMOKE=1 to run Postgres migration parity checks",
)
def test_migration_lower_url_host_matches_python_helpers():
    migration = _load_migration_module()
    engine = create_engine(os.environ["DATABASE_URL"], future=True)
    samples = [
        "HTTPS://WWW.Example.COM:8443/Path?Q=1#Frag",
        "//Foo.com/bar",
        "HTTP://[FEDC:BA98::7654]/p",
    ]
    with engine.begin() as conn:
        conn.execute(text(migration._CREATE_FN.strip()))
        try:
            for s in samples:
                py_val = lower_url_host(s)
                row = conn.execute(
                    text("SELECT migration_0013_lower_url_host(:x) AS v"),
                    {"x": s},
                ).one()
                assert row.v == py_val, (s, row.v, py_val)
        finally:
            conn.execute(text(migration._DROP_FN))


@pytest.mark.skipif(
    os.environ.get("RECON_PG_MIGRATION_SMOKE", "").lower() not in {"1", "true", "yes"},
    reason="Set RECON_PG_MIGRATION_SMOKE=1 to run Postgres migration parity checks",
)
def test_migration_fn_idempotent_repeat_apply():
    """CREATE OR REPLACE and DROP behave when run twice (mirrors alembic re-run)."""
    migration = _load_migration_module()
    engine = create_engine(os.environ["DATABASE_URL"], future=True)
    with engine.begin() as conn:
        conn.execute(text(migration._CREATE_FN.strip()))
        conn.execute(text(migration._CREATE_FN.strip()))
        conn.execute(text(migration._DROP_FN))
        conn.execute(text(migration._DROP_FN))
