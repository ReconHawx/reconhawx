"""Tests for ``models.assets``."""

from __future__ import annotations

from models.assets import Certificate, Domain, Ip, Service, Url, Website


def test_ip_equality_and_hash_use_ip_and_discovery_source() -> None:
    a = Ip(ip="1.2.3.4")
    b = Ip(ip="1.2.3.4")
    c = Ip(ip="1.2.3.4", discovered_via_domain="example.com")
    assert a == b
    assert hash(a) == hash(b)
    assert a != c


def test_ip_equality_rejects_non_ip() -> None:
    assert Ip(ip="1.2.3.4") != "1.2.3.4"


def test_ip_to_dict_preserves_fields() -> None:
    d = Ip(ip="1.2.3.4", ptr="host.example", service_provider="p").to_dict()
    assert d["ip"] == "1.2.3.4"
    assert d["ptr"] == "host.example"
    assert d["service_provider"] == "p"


def test_domain_to_dict_allows_list_ip() -> None:
    d = Domain(name="sub.example.com", ip=["1.1.1.1"], is_wildcard=True).to_dict()
    assert d["name"] == "sub.example.com"
    assert d["ip"] == ["1.1.1.1"]
    assert d["is_wildcard"] is True


def test_service_defaults() -> None:
    svc = Service(ip="1.2.3.4", port=80)
    assert svc.protocol == ""
    assert svc.service_name == ""


def test_website_and_url_construct() -> None:
    w = Website(url="https://example.com", host="example.com", port=443)
    assert w.url == "https://example.com"
    u = Url(url="https://example.com/path", hostname="example.com")
    assert u.to_dict()["url"] == "https://example.com/path"


def test_certificate_constructs_with_required_fields() -> None:
    cert = Certificate(
        subject_dn="CN=example",
        subject_cn="example.com",
        valid_from="2023-01-01",
        valid_until="2024-01-01",
        issuer_dn="CN=CA",
        issuer_cn="CA",
        serial_number="deadbeef",
        fingerprint_hash="abc",
    )
    assert cert.subject_cn == "example.com"
