"""Tests for unified findings processor (no live NATS/DB)."""

from unittest.mock import AsyncMock, patch

import pytest

from services.unified_findings_processor import (
    FindingBatchResult,
    UnifiedFindingsProcessingResult,
    UnifiedFindingsProcessor,
)


@pytest.mark.asyncio
async def test_process_findings_requires_program_id():
    proc = UnifiedFindingsProcessor()
    with pytest.raises(ValueError, match="program_id is required"):
        await proc.process_findings_unified({"nuclei": []}, "")


@pytest.mark.asyncio
async def test_get_job_status_unknown_returns_none():
    proc = UnifiedFindingsProcessor()
    assert await proc.get_job_status("nonexistent-job-id") is None


@pytest.mark.asyncio
async def test_get_job_status_returns_summary():
    proc = UnifiedFindingsProcessor()
    job_id = "job-test-1"
    result = UnifiedFindingsProcessingResult(
        job_id=job_id,
        program_id="00000000-0000-0000-0000-000000000099",
        program_name="prog-x",
        status="completed",
        total_findings=1,
        processed_findings=1,
        success_count=1,
    )
    result.finding_results["nuclei"] = FindingBatchResult(
        finding_type="nuclei",
        total_count=1,
        success_count=1,
    )
    proc.active_jobs[job_id] = result
    try:
        st = await proc.get_job_status(job_id)
        assert st is not None
        assert st["job_id"] == job_id
        assert st["program_id"] == "00000000-0000-0000-0000-000000000099"
        assert st["program_name"] == "prog-x"
        assert st["summary"]["finding_types"]["nuclei"] == 1
    finally:
        proc.active_jobs.pop(job_id, None)


@pytest.mark.asyncio
async def test_publish_completion_uses_publish_immediate_for_rich_events():
    proc = UnifiedFindingsProcessor()
    result = UnifiedFindingsProcessingResult(job_id="j1", program_id="00000000-0000-0000-0000-000000000001", program_name="p1")
    result.finding_results["nuclei"] = FindingBatchResult(
        finding_type="nuclei",
        created_findings=[
            {"event": "finding.created", "record_id": "r1", "finding_type": "nuclei"},
        ],
    )
    with patch(
        "services.unified_findings_processor.publisher.publish_immediate",
        new_callable=AsyncMock,
    ) as mock_immediate:
        await proc._publish_completion_events(result)
    mock_immediate.assert_awaited()
    first_subject = mock_immediate.await_args_list[0].args[0]
    assert first_subject == "events.findings.nuclei.created"
