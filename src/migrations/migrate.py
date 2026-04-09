#!/usr/bin/env python3
"""
Thin wrapper: forwards to ``python -m alembic`` with the correct config and PYTHONPATH.

Prefer: ``./scripts/migrate.sh <command>`` from the repo root.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def main() -> None:
    migrations_dir = Path(__file__).resolve().parent
    repo_root = migrations_dir.parent.parent
    ini = migrations_dir / "alembic.ini"
    api_app = repo_root / "src" / "api" / "app"
    src = repo_root / "src"
    extra = f"{src}:{api_app}"
    env = os.environ.copy()
    prev = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = extra if not prev else f"{extra}{os.pathsep}{prev}"
    cmd = [sys.executable, "-m", "alembic", "-c", str(ini), *sys.argv[1:]]
    sys.exit(subprocess.call(cmd, env=env, cwd=str(repo_root)))


if __name__ == "__main__":
    main()
