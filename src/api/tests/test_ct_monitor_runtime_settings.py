"""Unit tests for CT monitor global runtime merge (system_settings)."""

from app.services.ct_monitor_runtime_settings import default_ct_monitor_runtime, merge_ct_monitor_runtime


def test_default_ct_monitor_runtime():
    d = default_ct_monitor_runtime()
    assert d["domain_refresh_interval"] == 300
    assert d["stats_interval"] == 60
    assert "ct_poll_interval" not in d


def test_merge_ct_monitor_runtime_partial():
    m = merge_ct_monitor_runtime({"stats_interval": 30, "domain_refresh_interval": 600})
    assert m["stats_interval"] == 30
    assert m["domain_refresh_interval"] == 600


def test_merge_ignores_unknown_and_invalid():
    m = merge_ct_monitor_runtime(
        {"ct_poll_interval": 15, "bad": 1, "domain_refresh_interval": "notint"}
    )
    assert m["domain_refresh_interval"] == 300
    assert "ct_poll_interval" not in m
