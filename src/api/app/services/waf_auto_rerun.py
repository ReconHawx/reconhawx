"""
Auto-schedule a one-time inline workflow rerun for WAF-skipped targets.

Runs when a workflow log is saved with ``result`` ``cancelled_waf`` or ``partial_waf``.
"""
from __future__ import annotations

import copy
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import yaml

from models.job import JobSchedule, JobType, ScheduledJobRequest, ScheduleType

logger = logging.getLogger(__name__)

HEAVY_HTTP_TASK_NAMES: Set[str] = frozenset(
    {"test_http", "crawl_website", "fuzz_website", "nuclei_scan", "screenshot_website", "wpscan"}
)

_INPUT_TYPE_TO_VALUE_TYPE: Dict[str, str] = {
    "url": "urls",
    "subdomain": "domains",
    "ip": "ips",
    "cidr": "cidrs",
    "service": "services",
    "certificate": "certificates",
}

_PRIORITY_MAPPING_KEYS = (
    "urls",
    "url",
    "targets",
    "hosts",
    "subdomains",
    "domains",
    "ips",
    "addresses",
    "services",
)


def _rerun_delay_seconds() -> int:
    try:
        return int(os.getenv("WAF_AUTO_RERUN_DELAY_SECONDS", "2100"))
    except ValueError:
        return 2100


@lru_cache(maxsize=1)
def _builtin_task_yaml() -> Dict[str, Any]:
    alt = os.getenv("RECON_TASK_DEFAULTS_PATH")
    if alt and Path(alt).is_file():
        path = Path(alt)
    else:
        path = Path(__file__).resolve().parent.parent / "recon_task_builtin_defaults.yaml"
    if not path.is_file():
        logger.warning("WAF auto-rerun: recon_task_builtin_defaults not found at %s", path)
        return {}
    with open(path, encoding="utf-8") as f:
        loaded = yaml.safe_load(f)
    return loaded if isinstance(loaded, dict) else {}


def _task_registry_name(task_row: Dict[str, Any]) -> str:
    return str(task_row.get("task_type") or task_row.get("name") or "").strip()


def _value_type_for_task(task_yaml: Dict[str, Any]) -> str:
    it = task_yaml.get("input_types")
    if isinstance(it, list) and it:
        key = str(it[0]).lower().strip()
    elif isinstance(it, str) and it.strip():
        key = it.lower().strip()
    else:
        key = "url"
    return _INPUT_TYPE_TO_VALUE_TYPE.get(key, "urls")


def _sanitize_slug(part: str, max_len: int = 48) -> str:
    slug = re.sub(r"[^\w\-]+", "_", part, flags=re.UNICODE).strip("_")
    if len(slug) > max_len:
        slug = slug[:max_len]
    return slug or "step"


def _pick_primary_mapping_key(input_mapping: Dict[str, Any]) -> Optional[str]:
    if not isinstance(input_mapping, dict) or not input_mapping:
        return None
    for k in _PRIORITY_MAPPING_KEYS:
        if k in input_mapping:
            return k
    for k, v in input_mapping.items():
        paths = [v] if isinstance(v, str) else (v if isinstance(v, list) else [])
        for p in paths:
            ps = str(p).split(".")
            if len(ps) >= 2 and ps[0] in ("inputs", "steps"):
                return k
    return next(iter(input_mapping.keys()))


def _waf_status_from_step_blob(inner: Any) -> Dict[str, Any]:
    """Resolve per-step ``waf_status`` dict.

    Runner payloads attach ``waf_status`` at the top level of each step blob (see
    ``TaskExecutor.get_step_status_data``). Some payloads may nest it under
    ``status`` instead.
    """
    if not isinstance(inner, dict):
        return {}
    top = inner.get("waf_status")
    if isinstance(top, dict) and top:
        return top
    st = inner.get("status")
    if isinstance(st, dict):
        nested = st.get("waf_status")
        if isinstance(nested, dict):
            return nested
    return {}


def _extract_waf_targets_by_step(workflow_steps: Any) -> Dict[str, List[str]]:
    """step_name -> deduped skipped originals (from step status payloads)."""
    out: Dict[str, List[str]] = {}
    if not isinstance(workflow_steps, list):
        return out
    for blob in workflow_steps:
        if not isinstance(blob, dict) or len(blob) != 1:
            continue
        step_name = next(iter(blob))
        inner = blob[step_name]
        if not isinstance(inner, dict):
            continue
        ws = _waf_status_from_step_blob(inner)
        originals = ws.get("skipped_originals")
        raw_list = originals if isinstance(originals, list) else []
        keys = ws.get("blocked_all_nodes_keys")
        if (
            not raw_list
            and ws.get("skipped") == "waf_all_nodes_blocked"
            and isinstance(keys, list)
        ):
            raw_list = [str(x) for x in keys if x]
        if not raw_list:
            continue
        dedup: List[str] = []
        seen: Set[str] = set()
        for x in raw_list:
            s = str(x)
            if s not in seen:
                seen.add(s)
                dedup.append(s)
        out[step_name] = dedup
    return out


def _steps_by_name(steps_blob: Any) -> Dict[str, Dict[str, Any]]:
    idx: Dict[str, Dict[str, Any]] = {}
    if isinstance(steps_blob, list):
        for s in steps_blob:
            if isinstance(s, dict) and "name" in s:
                idx[str(s["name"])] = s
    return idx


async def maybe_schedule_waf_rerun(workflow_log: Optional[Dict[str, Any]]) -> Optional[str]:
    """If applicable, enqueue a one-time scheduled inline workflow rerun. Returns schedule_id or None."""
    from services.workflow_waf_auto_rerun_settings import get_workflow_waf_auto_rerun_effective

    policy = await get_workflow_waf_auto_rerun_effective()
    if not policy["enabled"]:
        logger.debug("WAF auto-rerun skipped: disabled in system settings")
        return None
    if not workflow_log or not isinstance(workflow_log, dict):
        return None

    raw_result = workflow_log.get("result")
    low = raw_result.lower() if isinstance(raw_result, str) else ""
    if low not in {"cancelled_waf", "partial_waf"}:
        return None

    execution_id = workflow_log.get("execution_id") or workflow_log.get("executionId")
    if not execution_id or not isinstance(execution_id, str):
        logger.warning("WAF auto-rerun: missing execution_id on workflow log")
        return None

    uid = workflow_log.get("user_id")
    if uid is None or str(uid).strip() == "":
        logger.warning(
            "WAF auto-rerun: workflow log %s has no user_id — skipping reschedule",
            execution_id,
        )
        return None

    program_name = workflow_log.get("program_name") or workflow_log.get("programName")
    if not program_name or not str(program_name).strip():
        logger.warning(
            "WAF auto-rerun: execution %s missing program_name — skipping",
            execution_id,
        )
        return None
    program_name = str(program_name).strip()

    wf_def = workflow_log.get("workflow_definition")
    if not isinstance(wf_def, dict):
        logger.warning("WAF auto-rerun: workflow_definition missing — skipping (%s)", execution_id)
        return None

    meta = wf_def.get("metadata")
    meta = meta if isinstance(meta, dict) else {}
    prev_attempt = meta.get("waf_rerun_attempt")
    try:
        prev_n = int(prev_attempt) if prev_attempt is not None else 0
    except (TypeError, ValueError):
        prev_n = 0
    next_attempt = prev_n + 1
    max_chain = policy["max_attempts"]
    if prev_n >= max_chain:
        logger.info(
            "WAF auto-rerun: execution %s at max attempts (%s) — skipping",
            execution_id,
            max_chain,
        )
        return None

    targets_map = _extract_waf_targets_by_step(workflow_log.get("workflow_steps"))
    if not targets_map:
        logger.info("WAF auto-rerun: no skipped_originals — skipping (%s)", execution_id)
        return None

    all_steps_raw = wf_def.get("steps") or []
    sid = _steps_by_name(all_steps_raw)
    orig_inputs = copy.deepcopy(wf_def.get("inputs") or {})
    if not isinstance(orig_inputs, dict):
        orig_inputs = {}

    new_inputs = copy.deepcopy(orig_inputs)
    rebuilt_steps: List[Dict[str, Any]] = []
    ty = _builtin_task_yaml()

    for step_name, skipped_vals in targets_map.items():
        step_def = sid.get(step_name)
        if not step_def:
            logger.warning("WAF auto-rerun: step %s not in workflow_definition — skipping", step_name)
            continue
        new_step = copy.deepcopy(step_def)
        tasks_row = new_step.get("tasks")
        if not isinstance(tasks_row, list):
            continue
        mutated = False
        for task in tasks_row:
            if not isinstance(task, dict):
                continue
            tname = _task_registry_name(task)
            if tname not in HEAVY_HTTP_TASK_NAMES:
                continue
            im = task.get("input_mapping") or {}
            if not isinstance(im, dict):
                continue
            slot_k = _pick_primary_mapping_key(im)
            if not slot_k:
                continue
            input_slot = (
                f"__waf_rerun_{_sanitize_slug(step_name)}"
                f"_{_sanitize_slug(task.get('name') or 'task')}"
                f"_{_sanitize_slug(slot_k)}"
            )
            vt = _value_type_for_task(ty.get(tname, {}))

            task["input_mapping"] = dict(im)
            task["input_mapping"][slot_k] = f"inputs.{input_slot}"

            new_inputs[input_slot] = {
                "type": "direct",
                "value_type": vt,
                "values": list(skipped_vals),
            }
            mutated = True
        if mutated:
            rebuilt_steps.append(new_step)

    if not rebuilt_steps:
        logger.warning("WAF auto-rerun: no heavy tasks could be remapped (%s)", execution_id)
        return None

    new_meta = {**meta, "parent_execution_id": execution_id, "waf_rerun_attempt": next_attempt, "source": "waf_auto_rerun"}
    wf_name = wf_def.get("name") or workflow_log.get("workflow_name") or "workflow"

    vars_copy = (
        wf_def["variables"].copy()
        if isinstance(wf_def.get("variables"), dict)
        else copy.deepcopy(wf_def.get("variables") or {})
    )
    prio = wf_def.get("priority")
    priority_str = str(prio).lower() if prio else str(workflow_log.get("priority") or "normal")

    runner_job_data = {
        "variables": vars_copy if isinstance(vars_copy, dict) else {},
        "inputs": new_inputs,
        "steps": rebuilt_steps,
        "metadata": new_meta,
        "priority": priority_str if priority_str in {"low", "normal", "high", "critical"} else "normal",
    }

    sched_label = (
        f"WAF rerun {execution_id.split('-')[0]} (#{next_attempt})"[:100]
        if isinstance(execution_id, str)
        else "WAF rerun"
    ).strip()

    descr = (
        f"Auto-rescheduled run for WAF-blocked targets (parent_execution_id={execution_id}, "
        f"workflow={wf_name})."
    )

    req = ScheduledJobRequest(
        job_type=JobType.WORKFLOW,
        job_data=runner_job_data,
        schedule=JobSchedule(
            schedule_type=ScheduleType.ONCE,
            start_time=datetime.now(timezone.utc)
            + timedelta(seconds=max(60, _rerun_delay_seconds())),
            timezone="UTC",
            enabled=True,
        ),
        name=sched_label,
        description=descr[:500],
        program_name=program_name,
        tags=["waf_auto_rerun", f"parent:{execution_id}"],
    )

    try:
        from repository.program_repo import ProgramRepository

        prog = await ProgramRepository.get_program_by_name(program_name)
        if not prog or not prog.get("id"):
            logger.error("WAF auto-rerun: program not found: %s", program_name)
            return None
        prog_id = str(prog["id"])
    except Exception as e:
        logger.exception("WAF auto-rerun: failed to resolve program %s: %s", program_name, e)
        return None

    try:
        from services.job_scheduler import scheduler_service

        created = await scheduler_service.create_scheduled_job(
            req,
            user_id=str(uid),
            program_ids=[prog_id],
        )
        sid_created = created.schedule_id
        logger.info(
            "WAF auto-rerun scheduled schedule_id=%s parent=%s attempt=%s",
            sid_created,
            execution_id,
            next_attempt,
        )
        return str(sid_created) if sid_created else None
    except Exception as e:
        logger.exception("WAF auto-rerun failed for execution %s: %s", execution_id, e)
        return None
