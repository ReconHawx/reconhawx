"""Tests for ``tasks.crawl_website.CrawlWebsite``."""

from __future__ import annotations

import base64
from unittest.mock import MagicMock, patch

import pytest

from tasks.base import AssetType
from tasks.crawl_website import CrawlWebsite


@pytest.fixture
def task() -> CrawlWebsite:
    return CrawlWebsite()


def test_get_timestamp_hash_is_reversible(task: CrawlWebsite) -> None:
    digest = task.get_timestamp_hash("https://example.com")
    decoded = base64.b64decode(digest).decode()
    assert "crawl_website" in decoded
    assert "https://example.com" in decoded


def test_get_command_uses_depth_and_timeout(task: CrawlWebsite) -> None:
    cmd = task.get_command(["https://example.com"], params={"depth": 3, "timeout": 60})
    assert "--depth 3" in cmd
    assert "--timeout 60" in cmd
    assert "https://example.com:443" in cmd


def test_get_command_default_depth_without_timeout(task: CrawlWebsite) -> None:
    cmd = task.get_command(["https://example.com"], params={})
    assert "--depth 5" in cmd
    assert "--timeout" not in cmd


def test_get_command_empty_on_no_valid_urls(task: CrawlWebsite) -> None:
    assert task.get_command(["not a url"], params={}) == ""
    assert task.get_command([], params={}) == ""


def test_parse_output_builds_url_assets_with_metadata(task: CrawlWebsite, load_fixture) -> None:
    # Avoid real DNS for katana-discovered redirect/final URLs in _process_entry.
    with patch("tasks.crawl_website.dns.resolver.Resolver") as mock_resolver_cls:
        mock_resolver_cls.return_value = MagicMock()
        raw = load_fixture("crawl_website/crawler_success.json")
        result = task.parse_output(raw)

    urls = result[AssetType.URL]
    # Expect a Url asset for each of: /, /about (from httpx) + /extra (katana only).
    hosts_paths = {(u.hostname, u.path) for u in urls}
    assert ("example.com", "/") in hosts_paths
    assert ("example.com", "/about") in hosts_paths
    assert ("example.com", "/extra") in hosts_paths

    root_url = next(u for u in urls if u.path == "/")
    assert root_url.title == "Example"
    assert root_url.technologies == ["Nginx"]
    assert root_url.http_status_code == 200
    # links from the wrapping dict flow into extracted_links
    assert root_url.extracted_links == ["https://other.test/x"]


def test_parse_output_deduplicates_via_normalize_url_for_comparison(task: CrawlWebsite) -> None:
    with patch("tasks.crawl_website.dns.resolver.Resolver"):
        raw = (
            '{"urls": {"https://example.com": {"httpx_output": '
            '"{\\"url\\": \\"https://example.com/x\\", \\"host\\": \\"example.com\\", \\"scheme\\": \\"https\\", \\"port\\": \\"443\\", \\"path\\": \\"/x\\", \\"a\\": [\\"1.2.3.4\\"], \\"time\\": \\"10ms\\", \\"failed\\": false}", '
            '"katana_output": "https://example.com/x", "links": {}}}}'
        )
        result = task.parse_output(raw)

    # Only one URL despite katana duplicating it.
    assert len(result[AssetType.URL]) == 1


def test_parse_output_empty_returns_empty(task: CrawlWebsite) -> None:
    assert task.parse_output("") == {AssetType.URL: []}


def test_parse_output_invalid_json_returns_empty(task: CrawlWebsite) -> None:
    assert task.parse_output("not json {{{") == {AssetType.URL: []}
