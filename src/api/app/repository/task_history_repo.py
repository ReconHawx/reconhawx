"""Materialize workflow task inputs into task_target_events for per-asset history."""

from __future__ import annotations

import ipaddress
import logging
import uuid as uuid_mod
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple
from urllib.parse import urlparse

from sqlalchemy import desc, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from db import SessionLocal
from models.base import utcnow
from models.postgres import (
    ApexDomain,
    Certificate,
    IP,
    Service,
    Subdomain,
    TaskTargetEvent,
    URL,
    WorkflowLog,
)

from utils.url_utils import lower_url_host, normalize_url_for_storage

logger = logging.getLogger(__name__)

_ASSET_TYPES = ("subdomain", "apex_domain", "ip", "url", "service", "certificate")


def _parse_ts(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        try:
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def collect_input_strings(input_data: Any) -> List[str]:
    """Extract comparable target strings from task_execution_logs input_data."""
    if input_data is None:
        return []
    if isinstance(input_data, str):
        s = input_data.strip()
        return [s] if s else []
    if isinstance(input_data, (int, float, bool)):
        return [str(input_data)]
    if isinstance(input_data, dict):
        d = input_data
        # Serialized runner Url models include hostname alongside url; the task target was the URL.
        url_val = d.get("url")
        if isinstance(url_val, str) and url_val.strip() and _looks_like_url(url_val):
            out_list = [url_val.strip()]
            final_val = d.get("final_url")
            if (
                isinstance(final_val, str)
                and final_val.strip()
                and _looks_like_url(final_val)
                and final_val.strip() != url_val.strip()
            ):
                out_list.append(final_val.strip())
            return out_list
        final_only = d.get("final_url")
        if isinstance(final_only, str) and final_only.strip() and _looks_like_url(final_only):
            return [final_only.strip()]

        out: List[str] = []
        for key in ("url", "name", "hostname", "ip", "ip_address", "target"):
            v = d.get(key)
            if isinstance(v, str) and v.strip():
                out.append(v.strip())
        if not out:
            for v in input_data.values():
                out.extend(collect_input_strings(v))
        return out
    if isinstance(input_data, list):
        acc: List[str] = []
        for item in input_data:
            acc.extend(collect_input_strings(item))
        return acc
    return []


def _looks_like_url(s: str) -> bool:
    sl = s.lower().strip()
    return sl.startswith("http://") or sl.startswith("https://")


def _is_plausible_ip(s: str) -> bool:
    try:
        ipaddress.ip_address(s.strip())
        return True
    except ValueError:
        return False


def url_match_variants(raw: str) -> Set[str]:
    """Build a small set of URL forms that may exist in urls.url."""
    variants: Set[str] = set()
    s = raw.strip()
    if not s:
        return variants
    variants.add(s)
    lowered = lower_url_host(s)
    if lowered:
        variants.add(lowered)
    norm_store = normalize_url_for_storage(s if _looks_like_url(s) else "")
    if norm_store:
        variants.add(norm_store)
        if norm_store.endswith("/") and len(norm_store) > 1:
            variants.add(norm_store.rstrip("/"))
        elif "/" not in norm_store.replace("://", ""):
            pass
        else:
            if not norm_store.endswith("/"):
                variants.add(norm_store + "/")
    if _looks_like_url(s):
        try:
            parsed = urlparse(s.lower())
            if parsed.scheme and parsed.hostname:
                port = parsed.port or (443 if parsed.scheme == "https" else 80)
                rootish = f"{parsed.scheme}://{parsed.hostname}:{port}/"
                variants.add(rootish)
                variants.add(rootish.rstrip("/"))
        except Exception:
            pass
    return {v for v in variants if v}


def hostnames_referenced_by_url_strings(url_strings: Sequence[str]) -> Set[str]:
    """Lowercase hostnames (no trailing dot) that appear in http(s) URL strings."""
    hosts: Set[str] = set()
    for s in url_strings:
        if not isinstance(s, str) or not s.strip():
            continue
        if not _looks_like_url(s):
            continue
        try:
            parsed = urlparse(s.strip().lower())
            if parsed.hostname:
                hosts.add(parsed.hostname.rstrip("."))
        except Exception:
            continue
    return hosts


def resolve_and_insert_task_targets_standalone(
    workflow_log_id: uuid_mod.UUID,
    program_id: uuid_mod.UUID,
    new_task_entries: Sequence[Dict[str, Any]],
) -> None:
    """Standalone DB session; failures are isolated from the workflow log transaction."""
    db = SessionLocal()
    try:
        resolve_and_insert_task_targets(db, workflow_log_id, program_id, new_task_entries)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def resolve_and_insert_task_targets(
    db: Session,
    workflow_log_id: uuid_mod.UUID,
    program_id: uuid_mod.UUID,
    new_task_entries: Sequence[Dict[str, Any]],
) -> None:
    if not new_task_entries:
        return

    rows: List[Dict[str, Any]] = []

    for entry in new_task_entries:
        if not isinstance(entry, dict):
            continue
        step_name = str(entry.get("step_name") or "")
        task_name = str(entry.get("task_name") or "")
        task_type = entry.get("task_type")
        task_type_s = str(task_type) if task_type is not None else None
        status = entry.get("status")
        status_s = str(status) if status is not None else None

        started = _parse_ts(entry.get("started_at")) or utcnow()
        completed = _parse_ts(entry.get("completed_at"))

        inputs = collect_input_strings(entry.get("input_data"))
        seen_pairs: Set[Tuple[str, uuid_mod.UUID]] = set()
        hosts_from_url_inputs = hostnames_referenced_by_url_strings(inputs)

        for raw in inputs:
            if not raw or not isinstance(raw, str):
                continue
            candidate = raw.strip()
            if not candidate:
                continue

            if _looks_like_url(candidate):
                variants = url_match_variants(candidate)
                if not variants:
                    continue
                q = (
                    db.query(URL.id)
                    .filter(
                        URL.program_id == program_id,
                        URL.url.in_(list(variants)),
                    )
                    .all()
                )
                for (url_id,) in q:
                    key = ("url", url_id)
                    if key not in seen_pairs:
                        seen_pairs.add(key)
                        rows.append(
                            {
                                "workflow_log_id": workflow_log_id,
                                "program_id": program_id,
                                "step_name": step_name,
                                "task_name": task_name,
                                "task_type": task_type_s,
                                "asset_type": "url",
                                "asset_id": url_id,
                                "started_at": started,
                                "completed_at": completed,
                                "status": status_s,
                            }
                        )
                continue

            if _is_plausible_ip(candidate):
                q = (
                    db.query(IP.id)
                    .filter(
                        IP.program_id == program_id,
                        func.host(IP.ip_address) == candidate.strip(),
                    )
                    .all()
                )
                for (ip_id,) in q:
                    key = ("ip", ip_id)
                    if key not in seen_pairs:
                        seen_pairs.add(key)
                        rows.append(
                            {
                                "workflow_log_id": workflow_log_id,
                                "program_id": program_id,
                                "step_name": step_name,
                                "task_name": task_name,
                                "task_type": task_type_s,
                                "asset_type": "ip",
                                "asset_id": ip_id,
                                "started_at": started,
                                "completed_at": completed,
                                "status": status_s,
                            }
                        )
                continue

            host = candidate.lower().rstrip(".")
            if not host:
                continue

            # URL-targeted runs may also list the bare hostname; do not attach subdomain/apex.
            if host in hosts_from_url_inputs:
                continue

            subs = (
                db.query(Subdomain.id)
                .filter(
                    Subdomain.program_id == program_id,
                    Subdomain.name == host,
                )
                .all()
            )
            for (sid,) in subs:
                key = ("subdomain", sid)
                if key not in seen_pairs:
                    seen_pairs.add(key)
                    rows.append(
                        {
                            "workflow_log_id": workflow_log_id,
                            "program_id": program_id,
                            "step_name": step_name,
                            "task_name": task_name,
                            "task_type": task_type_s,
                            "asset_type": "subdomain",
                            "asset_id": sid,
                            "started_at": started,
                            "completed_at": completed,
                            "status": status_s,
                        }
                    )

            apex_rows = (
                db.query(ApexDomain.id)
                .filter(
                    ApexDomain.program_id == program_id,
                    ApexDomain.name == host,
                )
                .all()
            )
            for (aid,) in apex_rows:
                key = ("apex_domain", aid)
                if key not in seen_pairs:
                    seen_pairs.add(key)
                    rows.append(
                        {
                            "workflow_log_id": workflow_log_id,
                            "program_id": program_id,
                            "step_name": step_name,
                            "task_name": task_name,
                            "task_type": task_type_s,
                            "asset_type": "apex_domain",
                            "asset_id": aid,
                            "started_at": started,
                            "completed_at": completed,
                            "status": status_s,
                        }
                    )

    if not rows:
        return

    batch_size = 500
    for i in range(0, len(rows), batch_size):
        chunk = rows[i : i + batch_size]
        stmt = insert(TaskTargetEvent).values(chunk).on_conflict_do_nothing(
            constraint="uq_task_target_event"
        )
        db.execute(stmt)


class TaskHistoryRepository:
    @staticmethod
    async def get_asset_program_id(asset_type: str, asset_id: str) -> Optional[uuid_mod.UUID]:
        """Return program_id for an asset row, or None if missing."""
        try:
            aid = uuid_mod.UUID(str(asset_id))
        except ValueError:
            return None

        from db import get_db_session

        async with get_db_session() as db:
            if asset_type == "subdomain":
                row = db.query(Subdomain.program_id).filter(Subdomain.id == aid).first()
            elif asset_type == "apex_domain":
                row = db.query(ApexDomain.program_id).filter(ApexDomain.id == aid).first()
            elif asset_type == "ip":
                row = db.query(IP.program_id).filter(IP.id == aid).first()
            elif asset_type == "url":
                row = db.query(URL.program_id).filter(URL.id == aid).first()
            elif asset_type == "service":
                row = db.query(Service.program_id).filter(Service.id == aid).first()
            elif asset_type == "certificate":
                row = db.query(Certificate.program_id).filter(Certificate.id == aid).first()
            else:
                return None
            if not row or row[0] is None:
                return None
            return row[0]

    @staticmethod
    async def get_task_history(
        *,
        asset_type: str,
        asset_id: uuid_mod.UUID,
        program_id: uuid_mod.UUID,
        limit: int,
        skip: int,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Return history rows and total count for pagination."""
        if asset_type not in _ASSET_TYPES:
            return [], 0

        from db import get_db_session

        async with get_db_session() as db:
            base = (
                db.query(TaskTargetEvent, WorkflowLog)
                .join(WorkflowLog, TaskTargetEvent.workflow_log_id == WorkflowLog.id)
                .filter(
                    TaskTargetEvent.asset_type == asset_type,
                    TaskTargetEvent.asset_id == asset_id,
                    TaskTargetEvent.program_id == program_id,
                )
            )
            total = base.count()

            results = (
                base.order_by(desc(TaskTargetEvent.started_at))
                .offset(skip)
                .limit(limit)
                .all()
            )

            items: List[Dict[str, Any]] = []
            for evt, wl in results:
                items.append(
                    {
                        "workflow_log_id": str(evt.workflow_log_id),
                        "execution_id": wl.execution_id,
                        "workflow_name": wl.workflow_name,
                        "step_name": evt.step_name,
                        "task_name": evt.task_name,
                        "task_type": evt.task_type,
                        "started_at": evt.started_at.isoformat() + "Z"
                        if evt.started_at
                        else None,
                        "completed_at": evt.completed_at.isoformat() + "Z"
                        if evt.completed_at
                        else None,
                        "status": evt.status,
                    }
                )
            return items, int(total)
