"""Tests for ``utils.utils``."""

from __future__ import annotations

import pytest

from utils.utils import (
    get_valid_domains,
    get_valid_ips,
    get_valid_urls,
    hostname_without_public_suffix,
    is_valid_domain,
    is_valid_ip,
    is_valid_url,
    normalize_url_for_comparison,
    normalize_url_for_storage,
    parse_url,
)


@pytest.mark.parametrize(
    "domain,expected",
    [
        ("example.com", True),
        ("sub.example.co.uk", True),
        ("", False),
        ("-leading.com", False),
        ("trailing-.com", False),
        ("example..com", False),
        ("bad", False),
        ("a" * 64 + ".com", False),
    ],
)
def test_is_valid_domain(domain: str, expected: bool) -> None:
    assert is_valid_domain(domain) is expected


def test_get_valid_domains() -> None:
    assert get_valid_domains(["ok.com", "bad..com", "test.org"]) == ["ok.com", "test.org"]


@pytest.mark.parametrize("ip,expected", [("1.2.3.4", True), ("not-an-ip", False), ("", False)])
def test_is_valid_ip(ip: str, expected: bool) -> None:
    assert is_valid_ip(ip) is expected


def test_get_valid_ips() -> None:
    assert get_valid_ips(["1.2.3.4", "bad", "5.6.7.8"]) == ["1.2.3.4", "5.6.7.8"]


def test_parse_url_normalizes_default_ports() -> None:
    result = parse_url("https://Example.com/foo")
    assert result["hostname"] == "example.com"
    assert result["port"] == 443
    assert result["scheme"] == "https"
    assert result["path"] == "/foo"


def test_parse_url_http_default_port() -> None:
    result = parse_url("http://example.com")
    assert result["port"] == 80
    assert result["path"] == "/"


def test_parse_url_invalid() -> None:
    assert parse_url("not-a-url") is False


def test_is_valid_url_adds_default_port() -> None:
    ok, std = is_valid_url("https://example.com")
    assert ok is True
    assert std == "https://example.com:443"


def test_is_valid_url_rejects_non_http() -> None:
    ok, std = is_valid_url("ftp://example.com")
    assert ok is False
    assert std == ""


def test_is_valid_url_rejects_empty() -> None:
    assert is_valid_url("") == (False, "")


def test_get_valid_urls_filters() -> None:
    urls = get_valid_urls(["https://example.com", "bad", "http://a.org:8080"])
    assert urls == ["https://example.com:443", "http://a.org:8080"]


def test_normalize_url_for_storage_roundtrip() -> None:
    assert normalize_url_for_storage("https://EXAMPLE.com") == "https://example.com:443/"
    assert normalize_url_for_storage("http://test.org:8080/path/") == "http://test.org:8080/path"
    assert normalize_url_for_storage("") == ""


def test_normalize_url_for_storage_invalid() -> None:
    assert normalize_url_for_storage("not-a-url") == ""


def test_normalize_url_for_comparison_strips_query_and_fragment() -> None:
    result = normalize_url_for_comparison("https://EXAMPLE.com/path?q=1#frag")
    assert result == "https://example.com:443/path"


def test_normalize_url_for_comparison_keeps_root_slash() -> None:
    assert normalize_url_for_comparison("http://a.com:8080/") == "http://a.com:8080/"


@pytest.mark.parametrize(
    "hostname,expected",
    [
        ("d0main.com", "d0main"),
        ("d0main.example.com", "d0main.example"),
        ("d0main.domain.co.uk", "d0main.domain"),
        ("www.example.co.uk", "www.example"),
        ("", None),
        ("nodot", None),
    ],
)
def test_hostname_without_public_suffix(hostname: str, expected: str | None) -> None:
    assert hostname_without_public_suffix(hostname) == expected
