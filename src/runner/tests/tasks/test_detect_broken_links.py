"""Tests for ``tasks.detect_broken_links.DetectBrokenLinks``."""

from __future__ import annotations

import base64

import pytest

from tasks.base import FindingType
from tasks.detect_broken_links import DetectBrokenLinks


@pytest.fixture
def task() -> DetectBrokenLinks:
    return DetectBrokenLinks()


def test_get_timestamp_hash_is_reversible(task: DetectBrokenLinks) -> None:
    digest = task.get_timestamp_hash("https://example.com")
    decoded = base64.b64decode(digest).decode()
    assert "detect_broken_links" in decoded
    assert "https://example.com" in decoded


def test_get_command_filters_to_http_urls_and_deduplicates(task: DetectBrokenLinks) -> None:
    cmd = task.get_command(
        [
            "https://example.com",
            "https://example.com",
            "ftp://nope.test",
            "not a url",
            "http://foo.test/path",
            "",
            None,
        ]
    )

    assert cmd.startswith("cat << 'EOF' | python3 check_broken_links.py\n")
    assert cmd.count("https://example.com") == 1
    assert "http://foo.test/path" in cmd
    assert "ftp://" not in cmd
    assert "not a url" not in cmd


def test_get_command_returns_empty_on_no_urls(task: DetectBrokenLinks) -> None:
    assert task.get_command([]) == ""
    assert task.get_command(["not a url"]) == ""


def test_parse_output_json_list(task: DetectBrokenLinks, load_fixture) -> None:
    raw = load_fixture("detect_broken_links/broken_links_findings.json")
    result = task.parse_output(raw)
    findings = result[FindingType.BROKEN_LINK]

    assert len(findings) == 2
    assert {f["broken_link"] for f in findings} == {
        "https://twitter.com/deleted_account",
        "https://abandoned.test/x",
    }


def test_parse_output_single_object(task: DetectBrokenLinks) -> None:
    raw = '{"url": "https://x.test", "broken_link": "https://y.test", "hijackable": false}'
    result = task.parse_output(raw)
    assert len(result[FindingType.BROKEN_LINK]) == 1


def test_parse_output_finds_json_in_mixed_lines(
    task: DetectBrokenLinks, load_fixture
) -> None:
    raw = load_fixture("detect_broken_links/broken_links_nonjson.txt")
    result = task.parse_output(raw)
    findings = result[FindingType.BROKEN_LINK]
    # 2 JSON lines embedded in a log stream; garbage skipped.
    assert len(findings) == 2
    assert {f["broken_link"] for f in findings} == {
        "https://dead.test/a",
        "https://dead.test/b",
    }


def test_parse_output_empty_returns_empty(task: DetectBrokenLinks) -> None:
    assert task.parse_output("") == {FindingType.BROKEN_LINK: []}


def test_parse_output_completely_unparseable_returns_empty(task: DetectBrokenLinks) -> None:
    assert task.parse_output("nothing to see here") == {FindingType.BROKEN_LINK: []}
