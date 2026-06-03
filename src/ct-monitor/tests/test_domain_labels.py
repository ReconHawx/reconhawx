"""Tests for tldextract-based hostname labels (ct-monitor)."""


def test_hostname_without_public_suffix_simple():
    from domain_labels import hostname_without_public_suffix

    assert hostname_without_public_suffix("domain.com") == "domain"
    assert hostname_without_public_suffix("d0main.com") == "d0main"


def test_hostname_without_public_suffix_multi_part_tld():
    from domain_labels import hostname_without_public_suffix

    assert hostname_without_public_suffix("d0main.domain.co.uk") == "d0main.domain"
    assert hostname_without_public_suffix("brand.co.uk") == "brand"


def test_hostname_without_public_suffix_subdomain():
    from domain_labels import hostname_without_public_suffix

    assert hostname_without_public_suffix("www.x.com") == "www.x"


def test_hostname_without_public_suffix_no_suffix():
    from domain_labels import hostname_without_public_suffix

    assert hostname_without_public_suffix("nodot") is None
    assert hostname_without_public_suffix("") is None


def test_extract_apex_domain_multi_part_tld():
    from domain_labels import extract_apex_domain

    assert extract_apex_domain("sub.example.co.uk") == "example.co.uk"
    assert extract_apex_domain("examp1e.co.uk") == "examp1e.co.uk"


def test_extract_apex_domain_public_suffix_only_returns_unchanged(caplog):
    import logging

    from domain_labels import extract_apex_domain

    caplog.set_level(logging.WARNING)
    for host in ("go.id", "my.id", "com.br"):
        assert extract_apex_domain(host) == host
    assert not any(
        "Could not extract apex domain" in r.message for r in caplog.records
    )


def test_extract_apex_domain_example_under_public_suffix():
    from domain_labels import extract_apex_domain

    assert extract_apex_domain("example.go.id") == "example.go.id"
