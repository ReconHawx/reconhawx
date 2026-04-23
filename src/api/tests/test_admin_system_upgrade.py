"""Tests for admin in-cluster upgrade routes."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from kubernetes.client.rest import ApiException

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
async def test_upgrade_status(client: httpx.AsyncClient, superuser_override):
    with patch("routes.admin_system_upgrade.KubernetesService") as K:
        inst = K.return_value
        cm = MagicMock()
        cm.data = {"APP_VERSION": "0.19.0"}
        inst.v1.read_namespaced_config_map.return_value = cm
        inst.list_upgrade_jobs.return_value = []
        with patch(
            "routes.admin_system_upgrade._fetch_github_latest_tag",
            new_callable=AsyncMock,
            return_value=("0.20.0", True),
        ):
            r = await client.get("/admin/system/upgrade/status")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "success"
    assert body["cluster_version"] == "0.19.0"
    assert body["latest_release"] == "0.20.0"
    assert body["github_reachable"] is True


@pytest.mark.asyncio
async def test_upgrade_status_no_configmap(client: httpx.AsyncClient, superuser_override):
    with patch("routes.admin_system_upgrade.KubernetesService") as K:
        inst = K.return_value
        inst.v1.read_namespaced_config_map.side_effect = ApiException(status=404)
        inst.list_upgrade_jobs.return_value = []
        with patch(
            "routes.admin_system_upgrade._fetch_github_latest_tag",
            new_callable=AsyncMock,
            return_value=(None, False),
        ):
            r = await client.get("/admin/system/upgrade/status")
    assert r.status_code == 200
    body = r.json()
    assert body["cluster_version"] is None
    assert body["github_reachable"] is False


@pytest.mark.asyncio
async def test_upgrade_job_bad_confirm(client: httpx.AsyncClient, superuser_override):
    r = await client.post(
        "/admin/system/upgrade/job",
        json={"version": "latest", "confirm": "WRONG"},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_upgrade_job_bad_version(client: httpx.AsyncClient, superuser_override):
    r = await client.post(
        "/admin/system/upgrade/job",
        json={"version": "not-a-version", "confirm": "UPGRADE_RECONHAWX"},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_upgrade_job_concurrent(client: httpx.AsyncClient, superuser_override):
    with patch("routes.admin_system_upgrade.KubernetesService") as K:
        inst = K.return_value
        inst.has_non_terminal_upgrade_job.return_value = True
        r = await client.post(
            "/admin/system/upgrade/job",
            json={"version": "latest", "confirm": "UPGRADE_RECONHAWX"},
        )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_upgrade_job_creates(client: httpx.AsyncClient, superuser_override):
    with patch("routes.admin_system_upgrade.KubernetesService") as K:
        inst = K.return_value
        inst.has_non_terminal_upgrade_job.return_value = False
        inst.create_upgrade_job = MagicMock()
        with patch("routes.admin_system_upgrade.ActionLogRepository.log_action", new_callable=AsyncMock):
            r = await client.post(
                "/admin/system/upgrade/job",
                json={"version": "latest", "kueue_resync_quotas": True, "confirm": "UPGRADE_RECONHAWX"},
            )
    assert r.status_code == 200
    assert r.json()["job_name"].startswith("reconhawx-upgrade-")
    inst.create_upgrade_job.assert_called_once()
    kw = inst.create_upgrade_job.call_args.kwargs
    assert kw["target_version"] == "latest"
    assert kw["kueue_resync_quotas"] is True
    assert kw["upgrade_observability"] is False


@pytest.mark.asyncio
async def test_upgrade_job_with_staging(client: httpx.AsyncClient, superuser_override):
    fake_sf = MagicMock()
    fake_sf.pull_token = "tok"
    with patch("routes.admin_system_upgrade.KubernetesService") as K:
        inst = K.return_value
        inst.has_non_terminal_upgrade_job.return_value = False
        inst.create_upgrade_job = MagicMock()
        with patch("routes.admin_system_upgrade.upgrade_staging.get_staging", return_value=fake_sf):
            with patch("routes.admin_system_upgrade.ActionLogRepository.log_action", new_callable=AsyncMock):
                r = await client.post(
                    "/admin/system/upgrade/job",
                    json={
                        "version": "0.20.0",
                        "staging_id": "a" * 16,
                        "confirm": "UPGRADE_RECONHAWX",
                    },
                )
    assert r.status_code == 200
    kw = inst.create_upgrade_job.call_args.kwargs
    assert kw["pull_token"] == "tok"
    assert kw["staging_id"] == "a" * 16


@pytest.mark.asyncio
async def test_maintenance_middleware_allows_system_upgrade_status(
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
    with patch("routes.admin_system_upgrade.KubernetesService") as K:
        inst = K.return_value
        inst.v1.read_namespaced_config_map.side_effect = ApiException(status=404)
        inst.list_upgrade_jobs.return_value = []
        with patch(
            "routes.admin_system_upgrade._fetch_github_latest_tag",
            new_callable=AsyncMock,
            return_value=(None, False),
        ):
            r = await client.get("/admin/system/upgrade/status")
    assert r.status_code == 200
