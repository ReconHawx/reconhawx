"""Tests for maintenance settings and middleware."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.main import app
from app.models.user_postgres import UserResponse
from auth.dependencies import require_superuser


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
async def test_maintenance_middleware_503_when_db_enabled(client: httpx.AsyncClient, monkeypatch):
    monkeypatch.setenv("DISABLE_MAINTENANCE_MIDDLEWARE", "false")

    async def fake_effective():
        return True, "Down for restore", {"db_enabled": True, "env_override_active": False}

    monkeypatch.setattr(
        "middleware.maintenance.maint_cfg.get_effective_maintenance",
        fake_effective,
    )
    r = await client.get("/programs")
    assert r.status_code == 503
    assert r.json().get("code") == "maintenance"


@pytest.mark.asyncio
async def test_maintenance_middleware_allows_auth_login(client: httpx.AsyncClient, monkeypatch):
    monkeypatch.setenv("DISABLE_MAINTENANCE_MIDDLEWARE", "false")

    async def fake_effective():
        return True, "Maint", {}

    monkeypatch.setattr(
        "middleware.maintenance.maint_cfg.get_effective_maintenance",
        fake_effective,
    )
    r = await client.post("/auth/login", json={})
    assert r.status_code != 503


@pytest.mark.asyncio
async def test_maintenance_middleware_allows_admin_database(
    client: httpx.AsyncClient,
    superuser_override,
    monkeypatch,
):
    monkeypatch.setenv("DISABLE_MAINTENANCE_MIDDLEWARE", "false")

    async def fake_effective():
        return True, "Maint", {}

    monkeypatch.setattr(
        "middleware.maintenance.maint_cfg.get_effective_maintenance",
        fake_effective,
    )
    with patch(
        "routes.admin_database.dbs.get_database_status",
        new_callable=AsyncMock,
        return_value={
            "database_name": "x",
            "postgres_host": "h",
            "postgres_port": 5432,
            "pg_dump_available": True,
            "pg_restore_available": True,
            "server_version": "15",
            "database_size_bytes": 1,
            "maintenance_effective": True,
            "maintenance_env_override": False,
        },
    ):
        r = await client.get("/admin/database/status")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_put_maintenance_settings(
    client: httpx.AsyncClient,
    superuser_override,
):
    with patch(
        "routes.admin_database_maintenance.AdminRepository.set_system_setting",
        new_callable=AsyncMock,
    ) as upsert:
        upsert.return_value = {"key": "maintenance_mode", "value": {"enabled": True, "message": "x"}}
        with patch(
            "routes.admin_database_maintenance.ActionLogRepository.log_action",
            new_callable=AsyncMock,
        ):
            r = await client.put(
                "/admin/database/maintenance/settings",
                json={"enabled": True, "message": "hello"},
            )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "success"
    upsert.assert_awaited_once()
