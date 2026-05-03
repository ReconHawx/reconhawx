"""Tests for workflow WAF auto-rerun system_settings + admin routes."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.main import app
from app.models.user_postgres import UserResponse
from auth.dependencies import require_superuser

import services.workflow_waf_auto_rerun_settings as wset


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


def test_merge_stored_value_canonical_fallback() -> None:
    assert wset.merge_stored_value(None) == dict(wset.CANONICAL_DEFAULTS)
    assert wset.merge_stored_value({}) == dict(wset.CANONICAL_DEFAULTS)


def test_merge_stored_value_overrides() -> None:
    m = wset.merge_stored_value(
        {
            "enabled": False,
            "max_attempts": 7,
            "delay_seconds": 120,
            "quarantine_ttl": 600,
            "secondary_promote": 3,
            "secondary_window": 120,
        }
    )
    assert m == {
        "enabled": False,
        "max_attempts": 7,
        "delay_seconds": 120,
        "quarantine_ttl": 600,
        "secondary_promote": 3,
        "secondary_window": 120,
    }


def test_merge_stored_value_ignores_invalid_numeric_fields() -> None:
    m = wset.merge_stored_value(
        {
            "max_attempts": 1000,
            "delay_seconds": 30,
            "quarantine_ttl": 30,
            "secondary_promote": 0,
            "secondary_window": 10,
            "enabled": True,
        }
    )
    assert m["max_attempts"] == wset.CANONICAL_DEFAULTS["max_attempts"]
    assert m["delay_seconds"] == wset.CANONICAL_DEFAULTS["delay_seconds"]
    assert m["quarantine_ttl"] == wset.CANONICAL_DEFAULTS["quarantine_ttl"]
    assert m["secondary_promote"] == wset.CANONICAL_DEFAULTS["secondary_promote"]
    assert m["secondary_window"] == wset.CANONICAL_DEFAULTS["secondary_window"]


@pytest.mark.asyncio
async def test_get_workflow_waf_auto_rerun_effective_no_row_logs():
    with patch("repository.admin_repo.AdminRepository") as cls:
        inst = cls.return_value
        inst.get_system_setting = AsyncMock(return_value=None)
        eff = await wset.get_workflow_waf_auto_rerun_effective()
    assert eff == dict(wset.CANONICAL_DEFAULTS)


@pytest.mark.asyncio
async def test_reset_to_defaults_calls_set():
    with patch("repository.admin_repo.AdminRepository") as cls:
        inst = cls.return_value
        inst.set_system_setting = AsyncMock(return_value={"key": wset.WORKFLOW_WAF_AUTO_RERUN_KEY})
        out = await wset.reset_workflow_waf_auto_rerun_to_defaults()
    assert out == dict(wset.CANONICAL_DEFAULTS)
    inst.set_system_setting.assert_awaited_once()
    call_kw = inst.set_system_setting.await_args
    assert call_kw.args[0] == wset.WORKFLOW_WAF_AUTO_RERUN_KEY
    assert call_kw.args[1] == dict(wset.CANONICAL_DEFAULTS)


@pytest.mark.asyncio
async def test_get_route(client: httpx.AsyncClient, superuser_override):
    fake = {
        "settings": dict(wset.CANONICAL_DEFAULTS),
        "stored": dict(wset.CANONICAL_DEFAULTS),
        "canonical_defaults": dict(wset.CANONICAL_DEFAULTS),
        "max_attempts_cap": wset.MAX_AUTO_RERUN_ATTEMPTS_ADMIN,
        "bounds": wset.admin_bounds_payload(),
    }
    with patch(
        "services.workflow_waf_auto_rerun_settings.get_admin_payload",
        new_callable=AsyncMock,
        return_value=fake,
    ):
        r = await client.get("/admin/workflow-waf-auto-rerun-settings")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "success"
    assert body["settings"]["enabled"] is True
    assert body["settings"]["max_attempts"] == 3


@pytest.mark.asyncio
async def test_put_route(client: httpx.AsyncClient, superuser_override):
    updated = dict(wset.CANONICAL_DEFAULTS)
    updated["enabled"] = False
    payload_shell = {
        "settings": updated,
        "stored": updated,
        "canonical_defaults": dict(wset.CANONICAL_DEFAULTS),
        "max_attempts_cap": wset.MAX_AUTO_RERUN_ATTEMPTS_ADMIN,
        "bounds": wset.admin_bounds_payload(),
    }
    with patch(
        "services.workflow_waf_auto_rerun_settings.update_workflow_waf_auto_rerun_partial",
        new_callable=AsyncMock,
        return_value=updated,
    ) as up:
        with patch(
            "services.workflow_waf_auto_rerun_settings.get_admin_payload",
            new_callable=AsyncMock,
            return_value=payload_shell,
        ):
            r = await client.put("/admin/workflow-waf-auto-rerun-settings", json={"enabled": False})
    assert r.status_code == 200
    up.assert_awaited_once_with(
        enabled=False,
        max_attempts=None,
        delay_seconds=None,
        quarantine_ttl=None,
        secondary_promote=None,
        secondary_window=None,
    )


@pytest.mark.asyncio
async def test_reset_route(client: httpx.AsyncClient, superuser_override):
    merged = dict(wset.CANONICAL_DEFAULTS)
    fake = {
        "settings": merged,
        "stored": merged,
        "canonical_defaults": dict(wset.CANONICAL_DEFAULTS),
        "max_attempts_cap": wset.MAX_AUTO_RERUN_ATTEMPTS_ADMIN,
        "bounds": wset.admin_bounds_payload(),
    }
    with patch(
        "services.workflow_waf_auto_rerun_settings.reset_workflow_waf_auto_rerun_to_defaults",
        new_callable=AsyncMock,
        return_value=merged,
    ) as rs:
        with patch(
            "services.workflow_waf_auto_rerun_settings.get_admin_payload",
            new_callable=AsyncMock,
            return_value=fake,
        ):
            r = await client.post("/admin/workflow-waf-auto-rerun-settings/reset-to-defaults")
    assert r.status_code == 200
    rs.assert_awaited_once()
