"""Tests for ``services.waf_auto_rerun``."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import services.waf_auto_rerun as war


@pytest.fixture
def mock_waf_effective_policy():
    with patch(
        "services.workflow_waf_auto_rerun_settings.get_workflow_waf_auto_rerun_effective",
        new_callable=AsyncMock,
    ) as m:
        m.return_value = {"enabled": True, "max_attempts": 10}
        yield m


@pytest.fixture
def base_waf_log() -> dict:
    exec_id = "11111111-1111-1111-1111-111111111111"
    return {
        "execution_id": exec_id,
        "program_name": "program-a",
        "user_id": "aaaaaaaa-bbbb-bbbb-bbbb-cccccccccccc",
        "workflow_name": "WF",
        "result": "partial_waf",
        "workflow_definition": {
            "name": "Parent WF",
            "variables": {},
            "inputs": {},
            "priority": "normal",
            "metadata": {},
            "steps": [
                {
                    "name": "HeavyStep",
                    "tasks": [
                        {
                            "name": "c1",
                            "task_type": "crawl_website",
                            "input_mapping": {"urls": "inputs.src"},
                        }
                    ],
                }
            ],
        },
        "workflow_steps": [
            {
                "HeavyStep": {
                    "total_assets": 0,
                    "waf_status": {
                        "skipped_originals": [
                            "https://a.example/x",
                            "https://b.example/y",
                        ],
                    },
                }
            }
        ],
    }


@pytest.mark.asyncio
@patch(
    "repository.program_repo.ProgramRepository.get_program_by_name",
    new_callable=AsyncMock,
)
@patch(
    "services.job_scheduler.scheduler_service.create_scheduled_job",
    new_callable=AsyncMock,
)
async def test_partial_waf_schedules_inline_workflow_no_workflow_id(
    mock_sched: AsyncMock,
    mock_prog: AsyncMock,
    base_waf_log: dict,
    monkeypatch,
    mock_waf_effective_policy: AsyncMock,
):
    monkeypatch.setenv("WAF_AUTO_RERUN_DELAY_SECONDS", "90")
    mock_prog.return_value = {"id": "dddddddd-dddd-dddd-dddd-dddddddddddd"}
    mock_sched.return_value = MagicMock(schedule_id="sched-abc")

    sid = await war.maybe_schedule_waf_rerun(base_waf_log)
    assert sid == "sched-abc"
    mock_sched.assert_awaited_once()
    req = mock_sched.await_args.args[0]
    assert req.job_type.value == "workflow"
    assert req.job_data.get("workflow_id") is None
    assert len(req.job_data["steps"]) == 1
    slot = "__waf_rerun_HeavyStep_c1_urls"
    assert req.job_data["inputs"][slot]["type"] == "direct"
    assert req.job_data["inputs"][slot]["values"] == [
        "https://a.example/x",
        "https://b.example/y",
    ]
    assert req.job_data["steps"][0]["tasks"][0]["input_mapping"]["urls"] == f"inputs.{slot}"
    assert "waf_auto_rerun" in req.tags


@pytest.mark.asyncio
async def test_success_result_no_op(base_waf_log: dict, mock_waf_effective_policy: AsyncMock):
    base_waf_log["result"] = "success"
    assert await war.maybe_schedule_waf_rerun(base_waf_log) is None


@pytest.mark.asyncio
async def test_missing_user_id(base_waf_log: dict, mock_waf_effective_policy: AsyncMock):
    base_waf_log.pop("user_id", None)
    assert await war.maybe_schedule_waf_rerun(base_waf_log) is None


@pytest.mark.asyncio
async def test_waf_auto_rerun_off(base_waf_log: dict, mock_waf_effective_policy: AsyncMock):
    mock_waf_effective_policy.return_value = {"enabled": False, "max_attempts": 3}
    assert await war.maybe_schedule_waf_rerun(base_waf_log) is None


@pytest.mark.asyncio
async def test_max_attempts_blocks(base_waf_log: dict, mock_waf_effective_policy: AsyncMock):
    mock_waf_effective_policy.return_value = {"enabled": True, "max_attempts": 1}
    base_waf_log["workflow_definition"]["metadata"] = {"waf_rerun_attempt": 1}
    assert await war.maybe_schedule_waf_rerun(base_waf_log) is None


def test_extract_waf_targets_prefers_top_level_waf_status() -> None:
    steps = [
        {
            "step_1": {
                "waf_status": {"skipped_originals": ["https://x.example/"]},
            },
        },
    ]
    assert war._extract_waf_targets_by_step(steps) == {"step_1": ["https://x.example/"]}


def test_extract_waf_targets_nested_status_fallback() -> None:
    steps = [
        {
            "S": {
                "status": {"waf_status": {"skipped_originals": ["https://nested/"]}},
            },
        },
    ]
    assert war._extract_waf_targets_by_step(steps) == {"S": ["https://nested/"]}


def test_extract_waf_targets_blocked_keys_fallback() -> None:
    steps = [
        {
            "S": {
                "waf_status": {
                    "skipped": "waf_all_nodes_blocked",
                    "blocked_all_nodes_keys": ["https://k1"],
                },
            },
        },
    ]
    assert war._extract_waf_targets_by_step(steps) == {"S": ["https://k1"]}
