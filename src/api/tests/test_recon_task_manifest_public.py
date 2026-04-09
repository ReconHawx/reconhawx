"""Public recon task effective-parameters manifest route."""

import httpx
import pytest
from httpx import ASGITransport

from app.main import app


@pytest.mark.asyncio
async def test_public_effective_parameters_manifest_ok(monkeypatch):
    fake_tasks = {
        "resolve_domain": {"timeout": 120, "chunk_size": 10},
        "port_scan": {"timeout": 900},
    }

    class FakeAdminRepository:
        async def get_all_known_recon_task_parameters_manifest(self):
            return fake_tasks

    import routes.admin as admin_mod

    monkeypatch.setattr(admin_mod, "AdminRepository", FakeAdminRepository)

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.get("/admin/public/recon-tasks/effective-parameters")

    assert r.status_code == 200
    body = r.json()
    assert body["tasks"] == fake_tasks
