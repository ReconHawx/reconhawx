"""Tests for ``recon_tasks.crawl_website.CrawlWebsite``."""

from __future__ import annotations

import base64
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from recon_tasks.base import AssetType
from recon_tasks.crawl_website import CrawlWebsite


@pytest.fixture
def task() -> CrawlWebsite:
    return CrawlWebsite()


def test_get_timestamp_hash_is_reversible(task: CrawlWebsite) -> None:
    digest = task.get_timestamp_hash("https://example.com")
    decoded = base64.b64decode(digest).decode()
    assert "crawl_website" in decoded
    assert "https://example.com" in decoded


def test_get_command_uses_full_mode_depth_and_timeout(task: CrawlWebsite) -> None:
    cmd = task.get_command(["https://example.com"], params={"depth": 3, "timeout": 60})
    assert "--mode full" in cmd
    assert "--depth 3" in cmd
    assert "--timeout 60" in cmd
    assert "https://example.com:443" in cmd


def test_get_command_default_depth_without_timeout(task: CrawlWebsite) -> None:
    cmd = task.get_command(["https://example.com"], params={})
    assert "--mode full" in cmd
    assert "--depth 5" in cmd
    assert "--timeout" not in cmd


def test_get_command_empty_on_no_valid_urls(task: CrawlWebsite) -> None:
    assert task.get_command(["not a url"], params={}) == ""
    assert task.get_command([], params={}) == ""


def test_parse_output_builds_url_assets_with_metadata(task: CrawlWebsite, load_fixture) -> None:
    # Avoid real DNS for redirect/final URLs in _process_entry.
    with patch("recon_tasks.crawl_website.dns.resolver.Resolver") as mock_resolver_cls:
        mock_resolver_cls.return_value = MagicMock()
        raw = load_fixture("crawl_website/crawler_success.json")
        result = task.parse_output(raw)

    urls = result[AssetType.URL]
    # Httpx: / and /about (200). /missing is 404 (skipped).
    hosts_paths = {(u.hostname, u.path) for u in urls}
    assert ("example.com", "/") in hosts_paths
    assert ("example.com", "/about") in hosts_paths
    assert ("example.com", "/missing") not in hosts_paths

    root_url = next(u for u in urls if u.path == "/")
    assert root_url.title == "Example"
    assert root_url.technologies == ["Nginx"]
    assert root_url.http_status_code == 200
    assert root_url.url == "https://example.com:443/"
    assert root_url.scheme == "https"
    assert root_url.port == 443
    # links from the wrapping dict flow into extracted_links
    assert root_url.extracted_links == ["https://other.test/x"]


def test_parse_output_deduplicates_via_normalize_url_for_comparison(task: CrawlWebsite) -> None:
    with patch("recon_tasks.crawl_website.dns.resolver.Resolver"):
        raw = (
            '{"urls": {"https://example.com": {"httpx_output": '
            '"{\\"url\\": \\"https://example.com/x\\", \\"host\\": \\"example.com\\", \\"scheme\\": \\"https\\", \\"port\\": \\"443\\", \\"path\\": \\"/x\\", \\"a\\": [\\"1.2.3.4\\"], \\"time\\": \\"10ms\\", \\"failed\\": false}", '
            '"links": {}}}}'
        )
        result = task.parse_output(raw)

    # Katana echoes the httpx URL but does not add a second asset; Katana-only paths are omitted.
    assert len(result[AssetType.URL]) == 1


def test_parse_output_ignores_urls_without_httpx_probe(task: CrawlWebsite) -> None:
    """Only URLs with a passing httpx JSON line are persisted (envelope has no side-channel list)."""
    with patch("recon_tasks.crawl_website.dns.resolver.Resolver"):
        raw = (
            '{"urls": {"https://example.com:443": {"httpx_output": '
            '"{\\"url\\": \\"https://example.com/\\", \\"host\\": \\"example.com\\", '
            '\\"scheme\\": \\"https\\", \\"port\\": \\"443\\", \\"path\\": \\"/\\", '
            '\\"method\\": \\"GET\\", \\"status_code\\": 200, \\"failed\\": false}", '
            '"links": {}}}}'
        )
        result = task.parse_output(raw)
    urls = result[AssetType.URL]
    assert len(urls) == 1
    assert urls[0].path == "/"


def test_parse_output_extracted_links_fallback_matches_by_comparison(task: CrawlWebsite) -> None:
    """links_dict key differing by case/storage form still resolves via comparison fallback."""
    with patch("recon_tasks.crawl_website.dns.resolver.Resolver"):
        raw = (
            '{"urls": {"https://example.com": {"httpx_output": '
            '"{\\"url\\": \\"https://example.com/about\\", \\"scheme\\": \\"https\\", '
            '\\"status_code\\": 200, \\"failed\\": false}", '
            '"links": {"https://EXAMPLE.com:443/about": ["https://peer.example/a"]}}}}'
        )
        result = task.parse_output(raw)
    urls = result[AssetType.URL]
    assert len(urls) == 1
    assert urls[0].extracted_links == ["https://peer.example/a"]


def test_parse_output_glue_concatenated_timestamp_json_on_one_line(task: CrawlWebsite) -> None:
    """Two httpx objects glued without a newline split on {"timestamp": ...} markers."""
    with patch("recon_tasks.crawl_website.dns.resolver.Resolver"):
        glued = (
            '{"timestamp":"2024-01-01T00:00:00Z","url":"https://example.com/a",'
            '"scheme":"https","status_code":200,"failed":false}'
            '{"timestamp":"2024-01-01T00:00:01Z","url":"https://example.com/b",'
            '"scheme":"https","status_code":200,"failed":false}'
        )
        raw = json.dumps({"urls": {"https://example.com": {"httpx_output": glued, "links": {}}}})
        result = task.parse_output(raw)
    paths = {(u.hostname, u.path) for u in result[AssetType.URL]}
    assert ("example.com", "/a") in paths
    assert ("example.com", "/b") in paths


def test_parse_output_empty_returns_empty(task: CrawlWebsite) -> None:
    assert task.parse_output("") == {AssetType.URL: []}


def test_parse_output_invalid_json_returns_empty(task: CrawlWebsite) -> None:
    assert task.parse_output("not json {{{") == {AssetType.URL: []}


@pytest.mark.asyncio
async def test_generate_commands_phased_discover_then_probe_shards(task: CrawlWebsite) -> None:
    seed = "https://example.com"
    discover_txt = json.dumps(
        {
            "urls": {
                "https://example.com:443": {
                    "discovered": [
                        "https://example.com:443/",
                        "https://example.com:443/a",
                        "https://example.com:443/b",
                    ]
                }
            }
        }
    )
    fake_batch = MagicMock()
    jm = MagicMock()
    jm.spawn_batch = AsyncMock(return_value=fake_batch)
    jm.wait_for_batch = AsyncMock()
    jm.get_job_outputs = MagicMock(return_value={"t1": {"output": discover_txt}})
    jm.cleanup_batch = MagicMock()
    jm._ensure_k8s_service = MagicMock()
    jm.k8s_service = MagicMock()
    jm.k8s_service.list_worker_nodes.return_value = ["n1", "n2"]

    specs = await task.generate_commands(
        [seed],
        {"httpx_urls_per_job": 1, "depth": 2, "katana_timeout": 60},
        {"job_manager": jm, "waf_reputation": None, "step_name": "step"},
    )
    assert len(specs) == 4
    assert all("python3 crawl_website.py --mode probe" in s.command for s in specs)
    assert jm.spawn_batch.call_count == 1
    discover_call = jm.spawn_batch.call_args_list[0]
    assert discover_call[1]["commands"][0].startswith(
        "cat << 'EOF' | python3 crawl_website.py --mode discover"
    )
    assert specs[0].required_nodes == ["n1"]
    assert specs[1].required_nodes == ["n2"]
    assert specs[2].required_nodes == ["n1"]
    assert specs[3].required_nodes == ["n2"]
