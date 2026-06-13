"""Tests for CompiledScopeMatcher (port of API scope_patterns matching)."""


def _matcher(**kwargs):
    from scope_matcher import CompiledScopeMatcher

    return CompiledScopeMatcher(**kwargs)


def test_exact_pattern_matches_only_exact_host():
    m = _matcher(scope_domains=[{"pattern": "app.example.com", "wildcard": False}])
    assert m.matches("app.example.com")
    assert not m.matches("other.example.com")
    assert not m.matches("sub.app.example.com")
    assert not m.matches("example.com")


def test_wildcard_label_pattern_requires_subdomain():
    m = _matcher(scope_domains=[{"pattern": "*.example.com", "wildcard": True}])
    assert m.matches("api.example.com")
    assert m.matches("deep.api.example.com")
    # Leading-* structured pattern does not match the apex itself.
    assert not m.matches("example.com")
    assert not m.matches("evil-example.com")


def test_wildcard_flag_without_star_matches_apex_and_subdomains():
    m = _matcher(scope_domains=[{"pattern": "example.com", "wildcard": True}])
    assert m.matches("example.com")
    assert m.matches("api.example.com")
    assert not m.matches("notexample.com")


def test_internal_wildcard_label():
    m = _matcher(scope_domains=[{"pattern": "api.*.example.com", "wildcard": True}])
    assert m.matches("api.dev.example.com")
    assert not m.matches("api.example.com")
    assert not m.matches("web.dev.example.com")


def test_out_of_scope_takes_precedence():
    m = _matcher(
        scope_domains=[{"pattern": "*.example.com", "wildcard": True}],
        out_of_scope_domains=[{"pattern": "*.dev.example.com", "wildcard": True}],
    )
    assert m.matches("api.example.com")
    assert not m.matches("api.dev.example.com")


def test_legacy_regex_in_and_out_of_scope():
    m = _matcher(
        domain_regex=[r"^.*\.example\.org$"],
        out_of_scope_regex=[r"^internal\..*$"],
    )
    assert m.matches("api.example.org")
    assert not m.matches("internal.example.org")
    assert not m.matches("example.org")


def test_invalid_entries_are_skipped():
    m = _matcher(
        scope_domains=[
            {"pattern": "bad_pattern!", "wildcard": False},
            "not-a-dict",
            {"pattern": "good.example.com", "wildcard": False},
        ],
        domain_regex=["([unbalanced"],
    )
    assert m.has_in_scope_rules
    assert m.matches("good.example.com")
    assert not m.matches("bad_pattern!")


def test_no_in_scope_rules():
    m = _matcher()
    assert not m.has_in_scope_rules
    assert not m.matches("anything.example.com")


def test_hostname_normalization():
    m = _matcher(scope_domains=[{"pattern": "*.Example.COM", "wildcard": True}])
    assert m.matches("API.Example.Com")
    assert m.matches("api.example.com.")


def test_apex_roots_from_structured_patterns():
    m = _matcher(
        scope_domains=[
            {"pattern": "*.example.com", "wildcard": True},
            {"pattern": "app.other.io", "wildcard": False},
            {"pattern": "api.*.dev.example.co.uk", "wildcard": True},
        ]
    )
    assert m.apex_roots == {"example.com", "other.io", "example.co.uk"}


def test_apex_roots_from_legacy_regex():
    m = _matcher(domain_regex=[r"^.*\.example\.net$"])
    assert m.apex_roots == {"example.net"}
