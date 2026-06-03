"""Unit tests for CT monitor global runtime merge (system_settings)."""

from app.services.ct_monitor_runtime_settings import default_ct_monitor_runtime, merge_ct_monitor_runtime


def test_default_ct_monitor_runtime():
    d = default_ct_monitor_runtime()
    assert d["stats_interval"] == 60
    assert "domain_refresh_interval" not in d
    assert "ct_poll_interval" not in d


def test_merge_ct_monitor_runtime_partial():
    m = merge_ct_monitor_runtime({"stats_interval": 30})
    assert m["stats_interval"] == 30


def test_merge_ignores_unknown_and_invalid():
    m = merge_ct_monitor_runtime(
        {
            "ct_poll_interval": 15,
            "bad": 1,
            "domain_refresh_interval": 600,
            "stats_interval": "notint",
        }
    )
    assert m["stats_interval"] == 60
    assert "domain_refresh_interval" not in m
    assert "ct_poll_interval" not in m
