"""Tests for ``recon_tasks.screenshot_website.ScreenshotWebsite``."""

from __future__ import annotations

import base64
import io
import json
import tarfile
from unittest.mock import patch

import pytest

from recon_tasks.base import AssetType, FindingType
from recon_tasks.screenshot_website import ScreenshotWebsite


@pytest.fixture
def task() -> ScreenshotWebsite:
    return ScreenshotWebsite()


def _build_screenshot_archive(entries: dict[str, bytes]) -> str:
    """Build a base64-encoded tar.gz of ``{filename: content}`` entries."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, content in entries.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
    return base64.b64encode(buf.getvalue()).decode()


def _gowitness_entry(
    url: str,
    file_name: str,
    html: str | None = None,
    failed: bool = False,
    failed_reason: str = "",
) -> dict:
    """Build a gowitness JSONL entry; ``html`` (if given) is embedded as network content."""
    entry: dict = {
        "url": url,
        "final_url": url,
        "file_name": file_name,
        "failed": failed,
        "failed_reason": failed_reason,
        "network": [],
    }
    if html is not None:
        entry["network"] = [
            {
                "request_type": 0,
                "status_code": 200,
                "mime_type": "text/html",
                "url": url,
                "content": base64.b64encode(html.encode()).decode(),
            }
        ]
    return entry


def _jsonl_bytes(*entries: dict) -> bytes:
    return ("\n".join(json.dumps(e) for e in entries) + "\n").encode()


def test_get_timestamp_hash_is_reversible(task: ScreenshotWebsite) -> None:
    digest = task.get_timestamp_hash("https://example.com")
    assert "screenshot_website" in base64.b64decode(digest).decode()


def test_get_command_normalizes_and_emits_heredoc(task: ScreenshotWebsite) -> None:
    cmd = task.get_command(["https://Example.com", "HTTP://foo.test"])
    assert cmd.startswith("cat << 'EOF' | bash screenshotter.sh\n")
    # Hostnames are lowercased by get_valid_urls / normalize_url_for_storage.
    assert "https://example.com" in cmd
    assert "http://foo.test" in cmd


def test_get_command_returns_empty_on_no_valid_urls(task: ScreenshotWebsite) -> None:
    assert task.get_command(["not-a-url"]) == ""
    assert task.get_command([]) == ""


def test_parse_output_empty_returns_empty(task: ScreenshotWebsite) -> None:
    assert task.parse_output("") == {AssetType.SCREENSHOT: []}


def test_parse_output_invalid_base64_returns_empty(task: ScreenshotWebsite) -> None:
    assert task.parse_output("not*base64!") == {AssetType.SCREENSHOT: []}


def test_parse_output_non_gzip_payload_returns_empty(task: ScreenshotWebsite) -> None:
    # Valid base64 but not a gzip header.
    encoded = base64.b64encode(b"{\"error\": \"boom\"}" ).decode()
    assert task.parse_output(encoded) == {AssetType.SCREENSHOT: []}


def test_parse_output_gowitness_archive(task: ScreenshotWebsite) -> None:
    # URL comes from the JSONL entry (not the PNG filename), and text is extracted from
    # the entry's embedded HTML content without any mocking.
    entry = _gowitness_entry("https://example.com/", "example.png", html="<p>hi</p>")
    archive = _build_screenshot_archive(
        {
            "example.png": b"\x89PNG\r\n\x1a\nFAKE",
            "gowitness.jsonl": _jsonl_bytes(entry),
        }
    )

    result = task.parse_output(archive)

    screenshots = result[AssetType.SCREENSHOT]
    assert len(screenshots) == 1
    shot = screenshots[0]
    assert shot["filename"] == "example.png"
    assert shot["status"] == "captured"
    assert shot["image_size"] == len(b"\x89PNG\r\n\x1a\nFAKE")
    # image_data is base64 of the raw bytes.
    assert base64.b64decode(shot["image_data"]) == b"\x89PNG\r\n\x1a\nFAKE"
    assert shot["extracted_text"] == "hi"
    assert "example.com" in shot["url"]


def test_parse_output_falls_back_to_ocr_when_no_html_text(task: ScreenshotWebsite) -> None:
    # Entry with no network HTML content -> JSONL extraction yields nothing -> OCR fallback.
    entry = _gowitness_entry("http://only.example.com/", "only.png", html=None)
    archive = _build_screenshot_archive(
        {
            "only.png": b"\x89PNG\r\n\x1a\n",
            "gowitness.jsonl": _jsonl_bytes(entry),
        }
    )
    with patch(
        "recon_tasks.screenshot_website.extract_text_from_image_ocr",
        return_value="ocr-text",
    ):
        result = task.parse_output(archive)

    screenshots = result[AssetType.SCREENSHOT]
    assert len(screenshots) == 1
    assert screenshots[0]["extracted_text"] == "ocr-text"


def test_parse_output_no_jsonl_returns_empty(task: ScreenshotWebsite) -> None:
    # Without the JSONL there is no authoritative URL mapping, so nothing is emitted.
    archive = _build_screenshot_archive({"orphan.png": b"\x89PNG\r\n\x1a\n"})
    assert task.parse_output(archive) == {AssetType.SCREENSHOT: []}


def test_parse_output_skips_failed_and_missing_entries(task: ScreenshotWebsite) -> None:
    ok = _gowitness_entry("https://ok.example/", "ok.png", html="<p>hi</p>")
    failed = _gowitness_entry(
        "https://bad.example/", "", failed=True, failed_reason="timeout"
    )
    missing = _gowitness_entry("https://gone.example/", "gone.png", html="<p>x</p>")
    archive = _build_screenshot_archive(
        {
            "ok.png": b"\x89PNG\r\n\x1a\nA",
            # Note: no "gone.png" file, and the failed entry has no file_name.
            "gowitness.jsonl": _jsonl_bytes(ok, failed, missing),
        }
    )

    result = task.parse_output(archive)
    screenshots = result[AssetType.SCREENSHOT]
    assert len(screenshots) == 1
    assert "ok.example" in screenshots[0]["url"]


def test_transform_to_findings_maps_screenshots(task: ScreenshotWebsite) -> None:
    assets = {
        AssetType.SCREENSHOT: [
            {
                "url": "https://example.com/",
                "image_data": "abc123",
                "filename": "https---example.com---.png",
                "extracted_text": "hello",
            }
        ]
    }
    findings_map = task.transform_to_findings(
        assets,
        context={
            "program_name": "prog1",
            "workflow_id": "wf-1",
            "step_name": "shot_step",
        },
    )
    findings = findings_map[FindingType.TYPOSQUAT_SCREENSHOT]
    assert len(findings) == 1
    assert findings[0].url == "https://example.com/"
    assert findings[0].image_data == "abc123"
    assert findings[0].program_name == "prog1"
    assert findings[0].workflow_id == "wf-1"
    assert findings[0].step_name == "shot_step"
    assert findings[0].extracted_text == "hello"


def test_transform_to_findings_uses_env_fallback(task: ScreenshotWebsite, monkeypatch) -> None:
    monkeypatch.setenv("PROGRAM_NAME", "env-prog")
    monkeypatch.setenv("WORKFLOW_ID", "env-wf")
    assets = {
        AssetType.SCREENSHOT: [
            {"url": "https://x.test/", "image_data": "img", "filename": "x.png"}
        ]
    }
    findings_map = task.transform_to_findings(assets, context={})
    finding = findings_map[FindingType.TYPOSQUAT_SCREENSHOT][0]
    assert finding.program_name == "env-prog"
    assert finding.workflow_id == "env-wf"
    assert finding.step_name == "screenshot_website"


def test_transform_to_findings_empty_when_no_screenshots(task: ScreenshotWebsite) -> None:
    assert task.transform_to_findings({AssetType.SCREENSHOT: []}, context={}) == {}


def test_process_output_for_typosquat_mode(task: ScreenshotWebsite, monkeypatch) -> None:
    monkeypatch.setenv("PROGRAM_NAME", "p")
    monkeypatch.setenv("WORKFLOW_ID", "w")
    entry = _gowitness_entry("https://example.com/", "example.png", html="<p>hi</p>")
    archive = _build_screenshot_archive(
        {
            "example.png": b"\x89PNG\r\n\x1a\nFAKE",
            "gowitness.jsonl": _jsonl_bytes(entry),
        }
    )
    findings_map = task.process_output_for_typosquat_mode(archive, params={})

    findings = findings_map[FindingType.TYPOSQUAT_SCREENSHOT]
    assert len(findings) == 1
    assert findings[0].url
    assert findings[0].image_data
    assert findings[0].program_name == "p"
    assert findings[0].workflow_id == "w"
