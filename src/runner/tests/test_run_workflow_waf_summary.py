"""Unit tests for WAF summary aggregation in ``run-workflow.py`` (hyphenated script)."""
from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_run_workflow_module():
    app_dir = Path(__file__).resolve().parents[1] / "app"
    path = app_dir / "run-workflow.py"
    spec = importlib.util.spec_from_file_location("_run_workflow_under_test", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_mod = _load_run_workflow_module()
_aggregate_waf_summary = _mod._aggregate_waf_summary
_derive_workflow_result = _mod._derive_workflow_result
_waf_step_fully_blocked = _mod._waf_step_fully_blocked


class TestWafStepFullyBlocked:
    def test_explicit_skipped_key(self) -> None:
        assert _waf_step_fully_blocked({"skipped": "waf_all_nodes_blocked", "task": "crawl_website"})

    def test_all_distinct_keys_blocked(self) -> None:
        assert _waf_step_fully_blocked(
            {
                "distinct_target_keys": 2,
                "blocked_all_nodes_keys": ["http://a.com:80", "http://b.com:80"],
                "skipped_inputs": 2,
            }
        )

    def test_partial_not_fully(self) -> None:
        assert not _waf_step_fully_blocked(
            {
                "distinct_target_keys": 3,
                "blocked_all_nodes_keys": ["http://a.com:80"],
                "skipped_inputs": 1,
            }
        )


class TestAggregateWafSummary:
    def test_empty_returns_no_skips(self) -> None:
        s, any_skips = _aggregate_waf_summary({})
        assert s == {} and not any_skips

        s2, any2 = _aggregate_waf_summary(None)  # type: ignore[arg-type]
        assert s2 == {} and not any2

    def test_no_skipped_inputs_ignored(self) -> None:
        s, any_skips = _aggregate_waf_summary(
            {"s1": {"candidate_nodes": ["n1"], "distinct_target_keys": 1, "skipped_inputs": 0}}
        )
        assert not any_skips

    def test_partial_only(self) -> None:
        step_waf = {
            "StepA": {
                "candidate_nodes": ["n1"],
                "distinct_target_keys": 2,
                "blocked_all_nodes_keys": ["http://t1:80"],
                "skipped_inputs": 1,
            }
        }
        s, any_skips = _aggregate_waf_summary(step_waf)
        assert any_skips
        assert s["fully_skipped_steps"] == []
        assert len(s["partial_skip_steps"]) == 1
        assert s["partial_skip_steps"][0]["step"] == "StepA"
        assert s["total_skipped_inputs"] == 1
        assert s["total_blocked_target_keys"] == 1
        assert "n1" in s["candidate_nodes_union"]

    def test_fully_skipped_explicit(self) -> None:
        step_waf = {
            "Heavy": {"skipped": "waf_all_nodes_blocked", "task": "crawl_website", "skipped_inputs": 3}
        }
        s, any_skips = _aggregate_waf_summary(step_waf)
        assert any_skips
        assert s["fully_skipped_steps"] == ["Heavy"]
        assert s["partial_skip_steps"] == []
        assert s["total_skipped_inputs"] == 3

    def test_mixed_prioritizes_fully_in_derive(self) -> None:
        step_waf = {
            "Heavy": {"skipped": "waf_all_nodes_blocked", "task": "foo", "skipped_inputs": 5},
            "Other": {
                "distinct_target_keys": 2,
                "blocked_all_nodes_keys": ["x"],
                "skipped_inputs": 1,
                "candidate_nodes": [],
            },
        }
        s, _ = _aggregate_waf_summary(step_waf)
        assert _derive_workflow_result("success", s) == "cancelled_waf"


class TestDeriveWorkflowResult:
    def test_non_success_unchanged(self) -> None:
        assert _derive_workflow_result("failed", {"any_skips": True}) == "failed"
        assert _derive_workflow_result("stopped", {}) == "stopped"

    def test_success_no_summary(self) -> None:
        assert _derive_workflow_result("success", None) == "success"
        assert _derive_workflow_result("success", {}) == "success"

    def test_success_partial_only(self) -> None:
        sm = {
            "any_skips": True,
            "fully_skipped_steps": [],
            "partial_skip_steps": [{"step": "A"}],
            "total_skipped_inputs": 1,
            "total_blocked_target_keys": 1,
            "candidate_nodes_union": [],
        }
        assert _derive_workflow_result("success", sm) == "partial_waf"

    def test_success_cancelled_waf(self) -> None:
        sm = {
            "any_skips": True,
            "fully_skipped_steps": ["H"],
            "partial_skip_steps": [],
            "total_skipped_inputs": 1,
            "total_blocked_target_keys": 1,
            "candidate_nodes_union": [],
        }
        assert _derive_workflow_result("success", sm) == "cancelled_waf"
