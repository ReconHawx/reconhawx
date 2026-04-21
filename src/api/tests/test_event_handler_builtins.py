"""Tests for built-in event handler YAML loading."""

from app.config.event_handler_builtins import get_system_handlers


def test_system_resolved_subdomain_recon_has_conditions_by_event_type():
    by_id = {h["id"]: h for h in get_system_handlers()}
    assert "system_resolved_subdomain_recon" in by_id
    h = by_id["system_resolved_subdomain_recon"]
    assert "assets.subdomain.created" in h["event_type"]
    assert "assets.subdomain.updated" in h["event_type"]
    cbt = h.get("conditions_by_event_type") or {}
    assert "assets.subdomain.created" in cbt
    assert "assets.subdomain.updated" in cbt
    assert any(c.get("field") == "new_ip_count" for c in cbt["assets.subdomain.updated"])
