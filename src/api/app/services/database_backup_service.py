"""
Logical backup of the application PostgreSQL database via pg_dump.

Database restore in production uses the cluster Job flow under /admin/database/maintenance/restore/*.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import tempfile
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, List, Literal, Optional

from sqlalchemy import text

from db import POSTGRES_DB, POSTGRES_HOST, POSTGRES_PASSWORD, POSTGRES_PORT, POSTGRES_USER, get_db_session
from repository.admin_repo import AdminRepository
from services import maintenance_settings as maint_settings

logger = logging.getLogger(__name__)

BackupFormat = Literal["custom", "plain"]

_MAX_RESTORE_BYTES_ENV = "DATABASE_RESTORE_MAX_BYTES"


def pg_client_binaries_available() -> Dict[str, bool]:
    return {
        "pg_dump": shutil.which("pg_dump") is not None,
        "pg_restore": shutil.which("pg_restore") is not None,
    }


def _pg_subprocess_env() -> Dict[str, str]:
    env = os.environ.copy()
    env["PGPASSWORD"] = POSTGRES_PASSWORD
    return env


def _pg_connection_args() -> List[str]:
    return [
        "-h",
        POSTGRES_HOST,
        "-p",
        str(POSTGRES_PORT),
        "-U",
        POSTGRES_USER,
        "-d",
        POSTGRES_DB,
    ]


def backup_filename_prefix(format: BackupFormat) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    ext = "dump" if format == "custom" else "sql"
    return f"reconhawx-{POSTGRES_DB}-{ts}.{ext}"


async def get_database_status() -> Dict[str, Any]:
    """Non-secret DB metadata for admin diagnostics."""
    tools = pg_client_binaries_available()
    version: Optional[str] = None
    size_bytes: Optional[int] = None
    try:
        async with get_db_session() as db:
            row = db.execute(text("SELECT version()")).fetchone()
            if row:
                version = row[0]
            row2 = db.execute(text("SELECT pg_database_size(current_database())")).fetchone()
            if row2:
                size_bytes = int(row2[0])
    except Exception as e:
        logger.error("database status query failed: %s", e)
        raise

    env_m = maint_settings.env_maintenance_active()
    try:
        repo = AdminRepository()
        row = await repo.get_system_setting(maint_settings.SYSTEM_SETTINGS_KEY)
        raw = (row or {}).get("value") if isinstance((row or {}).get("value"), dict) else {}
        db_m_enabled = bool(raw.get("enabled", False))
    except Exception:
        db_m_enabled = False

    return {
        "database_name": POSTGRES_DB,
        "postgres_host": POSTGRES_HOST,
        "postgres_port": int(POSTGRES_PORT) if str(POSTGRES_PORT).isdigit() else POSTGRES_PORT,
        "pg_dump_available": tools["pg_dump"],
        "pg_restore_available": tools["pg_restore"],
        "server_version": version,
        "database_size_bytes": size_bytes,
        "maintenance_effective": env_m or db_m_enabled,
        "maintenance_env_override": bool(env_m),
    }


async def run_pg_dump_to_tempfile(format: BackupFormat) -> str:
    """
    Run pg_dump to a temp file. Returns path; caller must delete after streaming.
    Raises RuntimeError on failure.
    """
    if not shutil.which("pg_dump"):
        raise RuntimeError("pg_dump is not installed or not on PATH")

    suffix = ".dump" if format == "custom" else ".sql"
    fd, path = tempfile.mkstemp(prefix="reconhawx-pgdump-", suffix=suffix)
    os.close(fd)
    try:
        cmd: List[str] = ["pg_dump", *_pg_connection_args(), "-f", path]
        if format == "custom":
            cmd.append("-Fc")
        else:
            cmd.extend(["-Fp", "--encoding", "UTF8"])

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            env=_pg_subprocess_env(),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        stderr_b = await proc.stderr.read()
        await proc.wait()
        if proc.returncode != 0:
            msg = stderr_b.decode(errors="replace").strip() or f"pg_dump exited {proc.returncode}"
            raise RuntimeError(msg)
        return path
    except Exception:
        try:
            os.unlink(path)
        except OSError:
            pass
        raise


async def iter_backup_file_chunks(path: str, chunk_size: int = 65536) -> AsyncIterator[bytes]:
    """Async generator reading file in chunks; deletes path when done."""

    def _read_chunk(f, size: int) -> bytes:
        return f.read(size)

    try:
        with open(path, "rb") as f:
            while True:
                chunk = await asyncio.to_thread(_read_chunk, f, chunk_size)
                if not chunk:
                    break
                yield chunk
    finally:
        try:
            os.unlink(path)
        except OSError as e:
            logger.warning("could not remove temp backup %s: %s", path, e)


def max_restore_upload_bytes() -> int:
    raw = os.getenv(_MAX_RESTORE_BYTES_ENV, str(5 * 1024**3))
    try:
        return max(1, int(raw))
    except ValueError:
        return 5 * 1024**3
