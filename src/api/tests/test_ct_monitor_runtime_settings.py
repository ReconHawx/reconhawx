"""Unit tests for CT monitor global runtime merge (system_settings)."""

from app.services.ct_monitor_runtime_settings import default_ct_monitor_runtime, merge_ct_monitor_runtime


def test_default_ct_monitor_runtime():
    d = default_ct_monitor_runtime()
    assert d["domain_refresh_interval"] == 300
    assert d["stats_interval"] == 60
    assert d["ct_poll_interval"] == 10
    assert d["ct_batch_size"] == 100
    assert d["ct_max_entries_per_poll"] == 1000
    assert d["ct_start_offset"] == 0


def test_merge_ct_monitor_runtime_partial():
    m = merge_ct_monitor_runtime({"ct_poll_interval": 15, "stats_interval": 30})
    assert m["ct_poll_interval"] == 15
    assert m["stats_interval"] == 30
    assert m["domain_refresh_interval"] == 300


def test_merge_ignores_unknown_and_invalid():
    m = merge_ct_monitor_runtime({"ct_batch_size": "200", "bad": 1, "domain_refresh_interval": "notint"})
    assert m["ct_batch_size"] == 200
    assert m["domain_refresh_interval"] == 300
