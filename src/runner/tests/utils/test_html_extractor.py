"""Tests for ``utils.html_extractor``."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from utils.html_extractor import (
    MAX_EXTRACTED_TEXT_BYTES,
    _extract_text_from_html,
    _truncate_text,
    _urls_match,
    extract_text_from_gowitness_entry,
    extract_text_from_gowitness_jsonl,
    load_gowitness_entries,
)


def test_extract_text_from_html_strips_scripts_and_styles() -> None:
    html = """
    <html><head><style>body{color:red}</style></head>
    <body><script>alert(1)</script>
    <h1>Hello</h1><p>World</p></body></html>
    """
    text = _extract_text_from_html(html)
    assert text is not None
    assert "Hello World" in text
    assert "alert" not in text
    assert "color:red" not in text


def test_extract_text_from_html_empty() -> None:
    assert _extract_text_from_html("") is None


def test_truncate_text_under_limit() -> None:
    assert _truncate_text("short text") == "short text"


def test_truncate_text_over_limit_adds_ellipsis() -> None:
    big = "a" * (MAX_EXTRACTED_TEXT_BYTES + 100)
    out = _truncate_text(big)
    assert out.endswith("...")
    assert len(out.encode("utf-8")) <= MAX_EXTRACTED_TEXT_BYTES


@pytest.mark.parametrize(
    "a,b,expected",
    [
        ("https://example.com/", "https://example.com", True),
        ("https://example.com:443/", "https://example.com/", True),
        ("https://example.com/", "http://example.com/", False),
        ("https://a.com/", "https://b.com/", False),
        ("https://example.com/foo", "https://example.com/foo/", True),
        ("", "https://x.com/", False),
    ],
)
def test_urls_match(a: str, b: str, expected: bool) -> None:
    assert _urls_match(a, b) is expected


def test_extract_text_from_gowitness_jsonl(tmp_path: Path) -> None:
    html = "<html><body><h1>Hi</h1></body></html>"
    entry = {
        "url": "https://example.com/",
        "final_url": "https://example.com/",
        "network": [
            {
                "request_type": 0,
                "status_code": 200,
                "mime_type": "text/html",
                "url": "https://example.com/",
                "content": base64.b64encode(html.encode()).decode(),
            }
        ],
    }
    path = tmp_path / "gowitness.jsonl"
    path.write_text(json.dumps(entry) + "\n")

    text = extract_text_from_gowitness_jsonl(str(path))
    assert text is not None
    assert "Hi" in text


def test_extract_text_from_gowitness_jsonl_empty(tmp_path: Path) -> None:
    path = tmp_path / "empty.jsonl"
    path.write_text("")
    assert extract_text_from_gowitness_jsonl(str(path)) is None


def test_extract_text_from_gowitness_jsonl_missing_file() -> None:
    assert extract_text_from_gowitness_jsonl("/does/not/exist.jsonl") is None


def test_extract_text_from_gowitness_jsonl_url_mismatch(tmp_path: Path) -> None:
    html = "<html><body>Hi</body></html>"
    entry = {
        "url": "https://other.com/",
        "final_url": "https://other.com/",
        "network": [
            {
                "request_type": 0,
                "status_code": 200,
                "mime_type": "text/html",
                "url": "https://other.com/",
                "content": base64.b64encode(html.encode()).decode(),
            }
        ],
    }
    path = tmp_path / "gw.jsonl"
    path.write_text(json.dumps(entry) + "\n")
    result = extract_text_from_gowitness_jsonl(str(path), url="https://example.com/")
    assert result is None


def test_extract_text_from_gowitness_entry_network_content() -> None:
    html = "<html><body><h1>Hi</h1></body></html>"
    entry = {
        "url": "https://example.com/",
        "final_url": "https://example.com/",
        "network": [
            {
                "request_type": 0,
                "status_code": 200,
                "mime_type": "text/html",
                "url": "https://example.com/",
                "content": base64.b64encode(html.encode()).decode(),
            }
        ],
    }
    text = extract_text_from_gowitness_entry(entry)
    assert text is not None
    assert "Hi" in text


def test_extract_text_from_gowitness_entry_top_html_fallback() -> None:
    # When network content is absent but the top-level html field is set (no --skip-html).
    entry = {
        "url": "https://example.com/",
        "final_url": "https://example.com/",
        "html": "<p>Fallback text</p>",
        "network": [],
    }
    assert extract_text_from_gowitness_entry(entry) == "Fallback text"


def test_extract_text_from_gowitness_entry_no_content_returns_none() -> None:
    entry = {
        "url": "https://example.com/",
        "final_url": "https://example.com/",
        "network": [
            {
                "request_type": 0,
                "status_code": 200,
                "mime_type": "text/html",
                "url": "https://example.com/",
                "content": None,
            }
        ],
    }
    assert extract_text_from_gowitness_entry(entry) is None


def test_extract_text_from_gowitness_entry_url_mismatch() -> None:
    entry = {
        "url": "https://other.com/",
        "final_url": "https://other.com/",
        "html": "<p>x</p>",
    }
    assert extract_text_from_gowitness_entry(entry, url="https://example.com/") is None


def test_load_gowitness_entries_skips_blank_and_malformed(tmp_path: Path) -> None:
    e1 = {"url": "https://a.com/"}
    e2 = {"url": "https://b.com/"}
    path = tmp_path / "gw.jsonl"
    path.write_text(json.dumps(e1) + "\n\n" + json.dumps(e2) + "\nnot-json\n")
    entries = load_gowitness_entries(str(path))
    assert [e["url"] for e in entries] == ["https://a.com/", "https://b.com/"]


def test_load_gowitness_entries_missing_file() -> None:
    assert load_gowitness_entries("/does/not/exist.jsonl") == []
