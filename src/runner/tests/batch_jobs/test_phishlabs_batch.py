"""Tests for pure helpers in ``batch_jobs.phishlabs_batch``."""

from __future__ import annotations

import pytest

from batch_jobs.phishlabs_batch import GoogleSafeBrowsingService, PhishLabsBatchTask


@pytest.fixture
def task(monkeypatch) -> PhishLabsBatchTask:
    monkeypatch.setenv("API_BASE_URL", "http://api:8000")
    monkeypatch.setenv("INTERNAL_SERVICE_API_KEY", "internal")
    return PhishLabsBatchTask(
        job_id="job-1", finding_ids=["f1", "f2"], user_id="u", action="fetch"
    )


def test_task_init_defaults(task: PhishLabsBatchTask) -> None:
    assert task.api_base_url == "http://api:8000"
    assert task.api_token == "internal"
    assert task.results["success_count"] == 0
    assert task.results["error_count"] == 0
    assert task.results["processed_findings"] == []


def test_group_findings_by_program_skips_missing_program(task: PhishLabsBatchTask) -> None:
    findings = [
        {"_id": "1", "program_name": "alpha"},
        {"_id": "2", "program_name": "beta"},
        {"_id": "3", "program_name": "alpha"},
        {"_id": "4"},
    ]
    grouped = task.group_findings_by_program(findings)
    assert sorted(grouped.keys()) == ["alpha", "beta"]
    assert len(grouped["alpha"]) == 2
    assert len(grouped["beta"]) == 1


@pytest.mark.asyncio
async def test_google_safe_browsing_service_report_succeeds() -> None:
    svc = GoogleSafeBrowsingService()
    result = await svc.report_domain("exarnple.com", program_name="prog")
    assert result["status"] == "success"
    assert result["domain"] == "exarnple.com"
    assert result["program_name"] == "prog"
    assert "reference_id" in result
