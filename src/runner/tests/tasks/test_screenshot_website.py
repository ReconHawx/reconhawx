"""Tests for ``tasks.screenshot_website.ScreenshotWebsite``."""

from __future__ import annotations

import base64
import io
import tarfile
from unittest.mock import patch

import pytest

from tasks.base import AssetType
from tasks.screenshot_website import ScreenshotWebsite


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
    archive = _build_screenshot_archive(
        {
            "https---example.com---.png": b"\x89PNG\r\n\x1a\nFAKE",
            "https---example.com---.jsonl": b'{"html": "<p>hi</p>"}',
        }
    )

    with patch(
        "tasks.screenshot_website.extract_text_from_gowitness_jsonl",
        return_value="hi",
    ), patch(
        "tasks.screenshot_website.extract_text_from_image_ocr",
        return_value="",
    ):
        result = task.parse_output(archive)

    screenshots = result[AssetType.SCREENSHOT]
    assert len(screenshots) == 1
    shot = screenshots[0]
    assert shot["filename"] == "https---example.com---.png"
    assert shot["status"] == "captured"
    assert shot["image_size"] == len(b"\x89PNG\r\n\x1a\nFAKE")
    # image_data is base64 of the raw bytes.
    assert base64.b64decode(shot["image_data"]) == b"\x89PNG\r\n\x1a\nFAKE"
    assert shot["extracted_text"] == "hi"
    assert "example.com" in shot["url"]


def test_parse_output_falls_back_to_ocr_when_no_jsonl(task: ScreenshotWebsite) -> None:
    archive = _build_screenshot_archive(
        {"http---only.example.com---.png": b"\x89PNG\r\n\x1a\n"}
    )
    with patch(
        "tasks.screenshot_website.extract_text_from_gowitness_jsonl",
        return_value=None,
    ), patch(
        "tasks.screenshot_website.extract_text_from_image_ocr",
        return_value="ocr-text",
    ):
        result = task.parse_output(archive)

    screenshots = result[AssetType.SCREENSHOT]
    assert len(screenshots) == 1
    assert screenshots[0]["extracted_text"] == "ocr-text"
