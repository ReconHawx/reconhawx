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


def test_skips_last_execution_filter(task) -> None:
    assert task.skips_last_execution_filter() is True


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


def test_get_command_skips_preflight_when_ignore_filtering(task, monkeypatch) -> None:
    calls: list[tuple] = []

    class FakeApiClient:
        def check_domain_filtering(self, domains, program_name):
            calls.append((domains, program_name))
            return {"filtered": domains, "allowed": []}

    task.api_client = FakeApiClient()
    monkeypatch.setattr(task, "_ensure_api_client", lambda: task.api_client)
    monkeypatch.setattr(
        task,
        "_build_worker_command_with_stdin",
        lambda variations, active_checks, geoip_checks, max_workers: ["echo worker"],
    )

    result = task.get_command(
        ["filtered.example.com"],
        {
            "analyze_input_as_variations": True,
            "include_subdomains": False,
            "ignore_typosquat_filtering": True,
        },
    )

    assert result == ["echo worker"]
    assert calls == []


def test_get_command_runs_preflight_without_ignore_filtering(task, monkeypatch) -> None:
    class FakeApiClient:
        def check_domain_filtering(self, domains, program_name):
            return {"filtered": ["filtered.example.com"], "allowed": []}

    task.api_client = FakeApiClient()
    monkeypatch.setattr(task, "_ensure_api_client", lambda: task.api_client)

    result = task.get_command(
        ["filtered.example.com"],
        {
            "analyze_input_as_variations": True,
            "include_subdomains": False,
            "ignore_typosquat_filtering": False,
        },
    )

    assert result == []


def test_get_command_selective_preflight_protected_seed_bypass(task, monkeypatch) -> None:
    calls: list[list[str]] = []
    built_variations: list[dict] = []

    class FakeApiClient:
        def check_domain_filtering(self, domains, program_name):
            calls.append(list(domains))
            return {"filtered": list(domains), "allowed": []}

    task.api_client = FakeApiClient()
    monkeypatch.setattr(task, "_ensure_api_client", lambda: task.api_client)
    monkeypatch.setattr(
        task.typosquat_analyzer,
        "_get_program_protected_domains",
        lambda program_name: ["brand.com"],
    )
    monkeypatch.setattr(
        task,
        "prepare_input_data",
        lambda input_data, params: [
            {"domain": "br4nd.com", "original_domain": "brand.com", "fuzzers": ["replacement"]},
            {"domain": "other.net", "original_domain": "other.org", "fuzzers": ["replacement"]},
        ],
    )

    def capture_build(variations, active_checks, geoip_checks, max_workers):
        built_variations.extend(variations)
        return ["echo worker"]

    monkeypatch.setattr(task, "_build_worker_command_with_stdin", capture_build)

    result = task.get_command(
        ["brand.com", "other.org"],
        {
            "analyze_input_as_variations": False,
            "include_subdomains": False,
            "ignore_typosquat_filtering": False,
        },
    )

    assert result == ["echo worker"]
    assert calls == [["other.net"]]
    assert len(built_variations) == 1
    assert built_variations[0]["domain"] == "br4nd.com"


def test_process_spawned_task_outputs_returns_screenshot_findings(task, monkeypatch) -> None:
    import io
    import json
    import tarfile

    from recon_tasks.base import FindingType

    # The gowitness JSONL entry drives the URL<->screenshot mapping and carries the HTML
    # body used for text extraction, matching the runner's parse_output flow.
    html = "<html><body><h1>Example</h1></body></html>"
    entry = {
        "url": "https://example.com/",
        "final_url": "https://example.com/",
        "file_name": "example.png",
        "failed": False,
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

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        png = b"\x89PNG\r\n\x1a\nFAKE"
        info = tarfile.TarInfo(name="example.png")
        info.size = len(png)
        tar.addfile(info, io.BytesIO(png))
        jsonl = (json.dumps(entry) + "\n").encode()
        jinfo = tarfile.TarInfo(name="gowitness.jsonl")
        jinfo.size = len(jsonl)
        tar.addfile(jinfo, io.BytesIO(jsonl))
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

    result = task.process_spawned_task_outputs()

    screenshots = result[FindingType.TYPOSQUAT_SCREENSHOT]
    assert len(screenshots) == 1
    assert screenshots[0].url
    assert screenshots[0].image_data
    assert screenshots[0].program_name == "prog"
