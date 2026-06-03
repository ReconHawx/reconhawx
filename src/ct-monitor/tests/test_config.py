"""Tests for CTMonitorConfig."""


def test_ct_monitor_config_explicit_kwargs():
    from config import CTMonitorConfig

    cfg = CTMonitorConfig(
        api_url="http://custom:9000",
        api_key="k",
        nats_url="nats://n:4222",
        enable_cache=False,
        ct_monitor_auto_start=False,
    )
    assert cfg.api_url == "http://custom:9000"
    assert cfg.api_key == "k"
    assert cfg.nats_url == "nats://n:4222"
    assert cfg.enable_cache is False
    assert cfg.ct_monitor_auto_start is False


def test_ct_enable_cache_explicit():
    from config import CTMonitorConfig

    assert CTMonitorConfig(enable_cache=True).enable_cache is True
    assert CTMonitorConfig(enable_cache=False).enable_cache is False


def test_ct_monitor_auto_start_explicit():
    from config import CTMonitorConfig

    assert CTMonitorConfig(ct_monitor_auto_start=True).ct_monitor_auto_start is True
    assert CTMonitorConfig(ct_monitor_auto_start=False).ct_monitor_auto_start is False


def test_ct_monitor_auto_start_env(monkeypatch):
    from config import CTMonitorConfig

    monkeypatch.delenv("CT_MONITOR_AUTO_START", raising=False)
    monkeypatch.setenv("CT_MONITOR_AUTO_START", "yes")
    assert CTMonitorConfig().ct_monitor_auto_start is True
    monkeypatch.setenv("CT_MONITOR_AUTO_START", "0")
    assert CTMonitorConfig().ct_monitor_auto_start is False


def test_certstream_url_default():
    from config import CTMonitorConfig

    cfg = CTMonitorConfig()
    assert cfg.ct_source == "certstream"
    assert cfg.certstream_url == "ws://certstream:4000/"


def test_certstream_url_from_env(monkeypatch):
    from config import CTMonitorConfig

    monkeypatch.setenv("CERTSTREAM_URL", "ws://localhost:4000/")
    assert CTMonitorConfig().certstream_url == "ws://localhost:4000/"


def test_ingestion_tld_filter_disabled_by_default(monkeypatch):
    from config import CTMonitorConfig

    monkeypatch.delenv("CT_INGESTION_TLD_FILTER_ENABLED", raising=False)
    assert CTMonitorConfig().ingestion_tld_filter_enabled is False


def test_certstream_scale_config_defaults(monkeypatch):
    from config import CTMonitorConfig

    monkeypatch.setenv("CT_CERTSTREAM_SCALE_ENABLED", "false")
    cfg = CTMonitorConfig()
    assert cfg.certstream_deployment_name == "certstream-server"
    assert cfg.kubernetes_namespace == "reconhawx"
    assert cfg.certstream_scale_enabled is False
    assert cfg.certstream_ready_timeout_sec == 90
