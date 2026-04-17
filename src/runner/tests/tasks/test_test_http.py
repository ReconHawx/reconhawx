"""Tests for ``tasks.test_http.TestHTTP`` (multi-type SUBDOMAIN+URL)."""

from __future__ import annotations

import base64

import pytest

from tasks.base import AssetType
from tasks.test_http import TestHTTP


@pytest.fixture
def task() -> TestHTTP:
    return TestHTTP()


def test_get_timestamp_hash_is_reversible(task: TestHTTP) -> None:
    digest = task.get_timestamp_hash("https://example.com")
    decoded = base64.b64decode(digest).decode()
    assert "test_http" in decoded
    assert "https://example.com" in decoded


def test_get_command_splits_urls_and_domains_into_two_commands(task: TestHTTP) -> None:
    commands = task.get_command(["https://example.com", "example.org"])

    assert isinstance(commands, list)
    assert len(commands) == 2

    url_cmd = next(c for c in commands if "https://example.com:443" in c)
    dom_cmd = next(c for c in commands if "example.org" in c and "-p " in c)

    # URL-only command does not include the -p port-sweep flag; domain command does.
    assert "-p " not in url_cmd
    assert "-p " in dom_cmd


def test_get_command_url_only_input_returns_one_command(task: TestHTTP) -> None:
    commands = task.get_command(["https://example.com"])
    assert len(commands) == 1
    assert "-p " not in commands[0]


def test_get_command_domain_only_input_returns_one_command(task: TestHTTP) -> None:
    commands = task.get_command(["example.org"])
    assert len(commands) == 1
    assert "-p " in commands[0]


def test_get_command_empty_input_returns_empty_list(task: TestHTTP) -> None:
    assert task.get_command([]) == []
    assert task.get_command(["not a url", "not a domain either"]) == []


def test_parse_output_httpx_multi_json(task: TestHTTP, load_fixture) -> None:
    raw = load_fixture("test_http/httpx_multi.jsonl")
    result = task.parse_output(raw)

    services = result[AssetType.SERVICE]
    urls = result[AssetType.URL]
    domains = result[AssetType.SUBDOMAIN]
    ips = result[AssetType.IP]
    certs = result[AssetType.CERTIFICATE]

    # 2 successful entries, each with one A record -> one service each.
    assert len(services) == 2
    assert {(s.ip, s.port) for s in services} == {("1.2.3.4", 443), ("5.6.7.8", 8443)}

    # Primary URL per entry; the failed entry is skipped entirely.
    primary_urls = {u.url for u in urls if u.hostname in ("example.com", "api.example.com")}
    assert "https://example.com/" in primary_urls or any(
        u.hostname == "example.com" for u in urls
    )

    # Domains include main hosts + certificate SANs (minus wildcards/IPs).
    names = {d.name for d in domains}
    assert "example.com" in names
    assert "api.example.com" in names
    assert "www.example.com" in names
    assert "*.example.com" not in names
    assert "192.168.1.1" not in names

    ip_strings = {ip.ip for ip in ips}
    assert ip_strings == {"1.2.3.4", "5.6.7.8"}

    assert len(certs) == 1
    cert = certs[0]
    assert cert.subject_cn == "example.com"
    assert cert.issuer_organization == ["DigiCert Inc"]
    assert cert.serial_number == "ABCDEF"


def test_parse_output_skips_failed_entries(task: TestHTTP) -> None:
    result = task.parse_output('{"failed": true, "url": "https://x.test"}')
    assert result[AssetType.SERVICE] == []
    assert result[AssetType.URL] == []


def test_parse_output_empty_returns_all_empty(task: TestHTTP) -> None:
    result = task.parse_output("")
    assert result[AssetType.SERVICE] == []
    assert result[AssetType.URL] == []
    assert result[AssetType.SUBDOMAIN] == []
    assert result[AssetType.IP] == []
    assert result[AssetType.CERTIFICATE] == []
