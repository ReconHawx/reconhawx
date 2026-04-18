"""Tests for per-program CT settings parsing."""


def test_default_tld_set_non_empty():
    import program_ct_settings

    assert "com" in program_ct_settings.default_tld_set()


def test_program_custom_tld_and_similarity():
    import program_ct_settings

    tlds, sim = program_ct_settings.program_tlds_and_similarity(
        {"ct_monitor_program_settings": {"tld_filter": "io,app", "similarity_threshold": 0.82}}
    )
    assert tlds == {"io", "app"}
    assert abs(sim - 0.82) < 1e-9


def test_program_empty_uses_defaults():
    import program_ct_settings

    tlds, sim = program_ct_settings.program_tlds_and_similarity(
        {"ct_monitor_program_settings": {"tld_filter": "", "similarity_threshold": None}}
    )
    assert tlds == program_ct_settings.default_tld_set()
    assert sim == program_ct_settings.DEFAULT_SIMILARITY_THRESHOLD
