"""Tests for per-program CT settings parsing."""


def test_default_tld_set_non_empty():
    import program_ct_settings

    assert "com" in program_ct_settings.default_tld_set()


def test_program_custom_tld_and_similarity_when_filter_enabled(monkeypatch):
    import program_ct_settings

    monkeypatch.setenv("CT_INGESTION_TLD_FILTER_ENABLED", "true")
    tlds, sim = program_ct_settings.program_tlds_and_similarity(
        {"ct_monitor_program_settings": {"tld_filter": "io,app", "similarity_threshold": 0.82}}
    )
    assert tlds == {"io", "app"}
    assert abs(sim - 0.82) < 1e-9


def test_program_empty_tld_no_default_when_filter_disabled(monkeypatch):
    import program_ct_settings

    monkeypatch.delenv("CT_INGESTION_TLD_FILTER_ENABLED", raising=False)
    tlds, sim = program_ct_settings.program_tlds_and_similarity(
        {"ct_monitor_program_settings": {"tld_filter": "", "similarity_threshold": None}}
    )
    assert tlds == set()
    assert sim == program_ct_settings.DEFAULT_SIMILARITY_THRESHOLD


def test_program_empty_tld_uses_default_when_filter_enabled(monkeypatch):
    import program_ct_settings

    monkeypatch.setenv("CT_INGESTION_TLD_FILTER_ENABLED", "true")
    tlds, sim = program_ct_settings.program_tlds_and_similarity(
        {"ct_monitor_program_settings": {"tld_filter": "", "similarity_threshold": None}}
    )
    assert tlds == program_ct_settings.default_tld_set()
    assert sim == program_ct_settings.DEFAULT_SIMILARITY_THRESHOLD


def test_build_domain_config_no_ingestion_tld_union(monkeypatch):
    import program_ct_settings
    from domain_config_builder import build_domain_config_from_loaded

    monkeypatch.delenv("CT_INGESTION_TLD_FILTER_ENABLED", raising=False)
    loaded = [
        (
            "prog1",
            {
                "ct_monitoring_enabled": True,
                "protected_domains": ["example.com"],
                "ct_monitor_program_settings": {"similarity_threshold": 0.8},
            },
        ),
    ]
    bundle = build_domain_config_from_loaded(loaded)
    assert bundle.ingestion_tld_union == set()
    assert bundle.programs_ct_enabled_detail[0]["tld_allowlist"] == "all"
