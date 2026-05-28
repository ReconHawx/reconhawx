"""Tests for ``recon_tasks.typosquat_detection.TyposquatDetection`` pure helpers.

Only covers paths that don't require Redis/API; init attaches component objects
whose network code is only called lazily.
"""

from __future__ import annotations

import base64

import pytest


@pytest.fixture(autouse=True)
def _disable_typosquat_cache(monkeypatch) -> None:
    monkeypatch.setenv("TYPOSQUAT_USE_CACHE", "false")


@pytest.fixture
def task():
    from recon_tasks.typosquat_detection import TyposquatDetection

    return TyposquatDetection()


def test_ensure_variation_format_from_strings(task) -> None:
    result = task._ensure_variation_format(["a.com", "b.com"], None)
    assert result == [
        {"domain": "a.com", "fuzzers": ["original"]},
        {"domain": "b.com", "fuzzers": ["original"]},
    ]


def test_ensure_variation_format_passes_dicts_through(task) -> None:
    items = [{"domain": "x.com", "fuzzers": ["homoglyph"]}]
    assert task._ensure_variation_format(items, None) == items


def test_ensure_variation_format_for_input_analysis_flags_subdomain(task) -> None:
    result = task._ensure_variation_format_for_input_analysis(
        ["a.com"], {"include_subdomains": True}
    )
    assert result[0]["domain"] == "a.com"
    assert result[0]["_subdomain_discovery_enabled"] is True
    assert result[0]["_is_input_domain_analysis"] is True


def test_get_timestamp_hash_encodes_task_name(task) -> None:
    digest = task.get_timestamp_hash("a.com", {"max_variations": 10})
    decoded = base64.b64decode(digest).decode()
    assert "a.com" in decoded
    assert "typosquat_detection" in decoded


def test_build_worker_command_with_stdin_chunks_and_flags(task) -> None:
    variations = [{"domain": f"v{i}.com", "fuzzers": ["insertion"]} for i in range(75)]
    commands = task._build_worker_command_with_stdin(
        variations, active_checks=True, geoip_checks=False, max_workers=3
    )
    # 75 variations chunked by 50 → 2 commands.
    assert len(commands) == 2
    for cmd in commands:
        assert "typosquat_worker.py" in cmd
        assert "--variations-stdin" in cmd
        assert "--workers 3" in cmd
        assert "--active" in cmd
        assert "--geoip" not in cmd


def test_process_spawned_task_outputs_returns_screenshot_findings(task, monkeypatch) -> None:
    import io
    import tarfile
    from unittest.mock import patch

    from recon_tasks.base import FindingType

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        content = b"\x89PNG\r\n\x1a\nFAKE"
        info = tarfile.TarInfo(name="https---example.com---.png")
        info.size = len(content)
        tar.addfile(info, io.BytesIO(content))
    archive_b64 = base64.b64encode(buf.getvalue()).decode()

    task.spawned_task_outputs = {"job-1": archive_b64}
    task.spawned_job_contexts = {
        "job-1": {
            "is_typosquat_screenshots": True,
            "program_name": "prog",
            "workflow_id": "wf-1",
            "step_name": "typosquat_detection",
        }
    }

    with patch(
        "recon_tasks.screenshot_website.extract_text_from_gowitness_jsonl",
        return_value=None,
    ), patch(
        "recon_tasks.screenshot_website.extract_text_from_image_ocr",
        return_value="",
    ):
        result = task.process_spawned_task_outputs()

    screenshots = result[FindingType.TYPOSQUAT_SCREENSHOT]
    assert len(screenshots) == 1
    assert screenshots[0].url
    assert screenshots[0].image_data
    assert screenshots[0].program_name == "prog"
