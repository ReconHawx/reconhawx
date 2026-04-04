"""Tests for admin database backup routes and service helpers."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.main import app
from app.models.user_postgres import UserResponse
from auth.dependencies import require_superuser
from services import database_backup_service as dbs


@pytest.fixture
def superuser_override():
    u = UserResponse(
        id="00000000-0000-0000-0000-000000000001",
        username="super",
        email="super@example.com",
        is_active=True,
        is_superuser=True,
        roles=["admin"],
        program_permissions={},
    )
    app.dependency_overrides[require_superuser] = lambda: u
    yield u
    app.dependency_overrides.pop(require_superuser, None)


@pytest.mark.asyncio
async def test_database_status_route(client: httpx.AsyncClient, superuser_override):
    payload = {
        "database_name": "reconhawx",
        "postgres_host": "postgresql",
        "postgres_port": 5432,
        "pg_dump_available": True,
        "pg_restore_available": True,
        "server_version": "PostgreSQL 15",
        "database_size_bytes": 4096,
    }
    with patch("routes.admin_database.dbs.get_database_status", new_callable=AsyncMock, return_value=payload):
        r = await client.get("/admin/database/status")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "success"
    assert body["database_name"] == "reconhawx"
    assert "backup_restore_feature_enabled" not in body


@pytest.mark.asyncio
async def test_database_backup_download(
    client: httpx.AsyncClient, superuser_override, tmp_path
):
    dump = tmp_path / "b.dump"
    dump.write_bytes(b"PGDMP-fake")

    async def fake_dump(fmt):
        return str(dump)

    with patch("routes.admin_database.dbs.run_pg_dump_to_tempfile", side_effect=fake_dump):
        with patch("routes.admin_database.ActionLogRepository.log_action", new_callable=AsyncMock):
            r = await client.get("/admin/database/backup")
    assert r.status_code == 200
    assert r.content == b"PGDMP-fake"
    assert "attachment" in r.headers.get("content-disposition", "")


@pytest.mark.asyncio
async def test_run_pg_dump_to_tempfile_reports_stderr():
    proc = MagicMock()
    proc.returncode = 1
    proc.wait = AsyncMock()
    proc.stderr.read = AsyncMock(return_value=b"missing extension")

    async def fake_exec(*_a, **_kw):
        return proc

    with patch("services.database_backup_service.asyncio.create_subprocess_exec", side_effect=fake_exec):
        with patch("services.database_backup_service.shutil.which", return_value="/usr/bin/pg_dump"):
            with pytest.raises(RuntimeError, match="missing extension"):
                await dbs.run_pg_dump_to_tempfile("custom")


def test_max_restore_upload_bytes_positive():
    assert dbs.max_restore_upload_bytes() >= 1024
