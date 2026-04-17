"""Public recon task effective-parameters manifest route."""

import httpx
import pytest
from httpx import ASGITransport

from app.main import app


@pytest.mark.asyncio
async def test_public_effective_parameters_manifest_ok(monkeypatch):
    fake_tasks = {
        "resolve_domain": {
            "parameters": {"timeout": 120, "chunk_size": 10},
            "input_types": ["subdomain"],
            "output_types": ["subdomain", "ip"],
        },
        "port_scan": {
            "parameters": {"timeout": 900},
            "input_types": ["ip"],
            "output_types": ["service"],
        },
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


def test_recon_task_api_payload_exposes_io_types_from_yaml():
    """
    Pure-python: the payload built from builtin YAML must expose input_types /
    output_types alongside parameters, with metadata stripped from parameters.
    """
    from recon_task_defaults import recon_task_api_payload

    payload = recon_task_api_payload("port_scan", None)
    assert payload["recon_task"] == "port_scan"
    assert payload["input_types"] == ["ip"]
    assert payload["output_types"] == ["service"]
    assert "input_types" not in payload["parameters"]
    assert "output_types" not in payload["parameters"]
    assert "timeout" in payload["parameters"]


def test_recon_task_api_payload_strips_metadata_from_stored_overrides():
    """Stored DB parameters that contain metadata keys must not leak into `parameters`."""
    from recon_task_defaults import recon_task_api_payload

    row = {
        "id": 1,
        "parameters": {"timeout": 42, "input_types": ["bogus"], "output_types": ["nope"]},
        "created_at": None,
        "updated_at": None,
    }
    payload = recon_task_api_payload("port_scan", row)
    assert payload["parameters"]["timeout"] == 42
    assert "input_types" not in payload["parameters"]
    assert "output_types" not in payload["parameters"]
    # YAML is the source of truth for io types even when a DB row exists
    assert payload["input_types"] == ["ip"]
    assert payload["output_types"] == ["service"]
