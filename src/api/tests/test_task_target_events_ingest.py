"""Unit tests for task target resolution helpers (ingest path)."""

import uuid
from unittest.mock import MagicMock

from repository.task_history_repo import (
    _should_materialize_task_log_entry,
    _task_log_input_payload,
    collect_input_strings,
    hostnames_referenced_by_url_strings,
    resolve_and_insert_task_targets,
    url_match_variants,
)


def test_collect_input_strings_from_list():
    assert collect_input_strings(["a.com", "b.com"]) == ["a.com", "b.com"]


def test_collect_input_strings_from_dict_name():
    assert collect_input_strings({"name": "host.example"}) == ["host.example"]


def test_collect_input_strings_nested():
    assert collect_input_strings([{"url": "https://x.test:443"}]) == ["https://x.test:443"]


def test_url_match_variants_https_root():
    v = url_match_variants("https://WWW.Example.COM")
    assert "https://www.example.com:443/" in v
    assert "https://www.example.com:443" in v


def test_url_match_variants_includes_lowered_original():
    v = url_match_variants("https://a.example:8443/path")
    assert any("8443" in x for x in v)


def test_collect_url_dict_omits_hostname():
    """Runner-serialized Url dicts must not also emit hostname as a separate target."""
    inp = {
        "url": "https://dummysite.h3x.it:443/",
        "hostname": "dummysite.h3x.it",
    }
    assert collect_input_strings(inp) == ["https://dummysite.h3x.it:443/"]


def test_collect_url_dict_includes_distinct_final_url():
    inp = {
        "url": "https://a.example:443/",
        "final_url": "https://b.example:443/",
        "hostname": "a.example",
    }
    out = collect_input_strings(inp)
    assert "https://a.example:443/" in out
    assert "https://b.example:443/" in out
    assert "a.example" not in out
    assert "b.example" not in out


def test_hostnames_referenced_by_url_strings():
    h = hostnames_referenced_by_url_strings(
        ["https://a.example:443", "b.example", "not a url"]
    )
    assert "a.example" in h
    assert "b.example" not in h


def test_task_log_input_payload_prefers_executed_input_data():
    entry = {
        "input_data": ["legacy.example"],
        "executed_input_data": ["ran.example"],
    }
    assert _task_log_input_payload(entry) == ["ran.example"]


def test_task_log_input_payload_falls_back_to_input_data():
    entry = {"input_data": ["legacy.example"]}
    assert _task_log_input_payload(entry) == ["legacy.example"]


def test_should_materialize_skipped_status():
    assert not _should_materialize_task_log_entry(
        {"status": "skipped", "input_data": ["a.example"]}
    )


def test_should_materialize_empty_executed_input():
    assert not _should_materialize_task_log_entry(
        {"status": "success", "executed_input_data": []}
    )


def test_should_materialize_legacy_success_with_input():
    assert _should_materialize_task_log_entry(
        {"status": "success", "input_data": ["a.example"]}
    )


def test_resolve_and_insert_skips_non_executed_entries():
    db = MagicMock()
    wf_id = uuid.uuid4()
    prog_id = uuid.uuid4()
    resolve_and_insert_task_targets(
        db,
        wf_id,
        prog_id,
        [
            {
                "step_name": "s1",
                "task_name": "test_http",
                "status": "skipped",
                "input_data": ["skipped.example"],
            },
            {
                "step_name": "s1",
                "task_name": "test_http",
                "status": "success",
                "executed_input_data": [],
            },
        ],
    )
    db.execute.assert_not_called()
