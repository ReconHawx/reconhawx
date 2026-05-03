"""Tests for GET /admin/worker-status."""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from app.main import app
from app.models.user_postgres import UserResponse
from auth.dependencies import require_authentication, require_superuser


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


@pytest.fixture
def admin_authenticated_override():
    u = UserResponse(
        id="00000000-0000-0000-0000-000000000002",
        username="admin",
        email="admin@example.com",
        is_active=True,
        is_superuser=False,
        roles=["admin"],
        program_permissions={},
    )

    async def _auth():
        return u

    app.dependency_overrides[require_authentication] = _auth
    yield u
    app.dependency_overrides.pop(require_authentication, None)


@pytest.mark.asyncio
async def test_worker_status_superuser_merges_cluster_and_orphans(
    client: httpx.AsyncClient, superuser_override
):
    fake_waf = {
        "redis_connected": True,
        "error": None,
        "blocked_by_node": {
            "worker-1": [
                {
                    "target": "https://a.example:443",
                    "vendor": None,
                    "source": "precheck",
                    "blocked_at": 1.0,
                    "ttl_seconds": 60,
                    "evidence": [],
                }
            ],
            "gone-node": [
                {
                    "target": "https://orphan:443",
                    "vendor": None,
                    "source": "secondary",
                    "blocked_at": 2.0,
                    "ttl_seconds": 30,
                    "evidence": [],
                }
            ],
        },
    }
    with patch("services.kubernetes.KubernetesService") as mock_k:
        mock_k.return_value.list_worker_nodes.return_value = [
            {"name": "worker-1", "ready": True},
            {"name": "worker-2", "ready": False},
        ]
        with patch("services.worker_waf_status.get_worker_waf_status", return_value=fake_waf):
            r = await client.get("/admin/worker-status")
    assert r.status_code == 200
    body = r.json()
    assert body["redis_connected"] is True
    assert body["redis_error"] is None
    rows = {row["name"]: row for row in body["nodes"]}
    assert rows["worker-1"]["blocked_count"] == 1
    assert rows["worker-1"]["orphan"] is False
    assert rows["worker-1"]["ready"] is True
    assert rows["worker-2"]["blocked_count"] == 0
    assert rows["worker-2"]["targets"] == []
    assert rows["gone-node"]["orphan"] is True
    assert rows["gone-node"]["ready"] is None
    assert rows["gone-node"]["blocked_count"] == 1


@pytest.mark.asyncio
async def test_worker_status_forbidden_for_non_superuser(
    client: httpx.AsyncClient, admin_authenticated_override
):
    r = await client.get("/admin/worker-status")
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_worker_status_redis_down_still_returns_nodes(
    client: httpx.AsyncClient, superuser_override
):
    fake_waf = {"redis_connected": False, "error": "boom", "blocked_by_node": {}}
    with patch("services.kubernetes.KubernetesService") as mock_k:
        mock_k.return_value.list_worker_nodes.return_value = [{"name": "w1", "ready": True}]
        with patch("services.worker_waf_status.get_worker_waf_status", return_value=fake_waf):
            r = await client.get("/admin/worker-status")
    assert r.status_code == 200
    body = r.json()
    assert body["redis_connected"] is False
    assert body["redis_error"] == "boom"
    assert len(body["nodes"]) == 1
    assert body["nodes"][0]["blocked_count"] == 0
