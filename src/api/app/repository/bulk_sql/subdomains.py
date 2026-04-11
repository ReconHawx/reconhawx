"""Chunked bulk upsert for subdomains (PostgreSQL)."""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from db import BatchSessionLocal
from models.postgres import ApexDomain, IP, Program, Subdomain, SubdomainIP
from repository.bulk_sql.config import sql_chunk_size
from repository.bulk_sql.scope import domain_in_scope
from utils.domain_utils import extract_apex_domain

logger = logging.getLogger(__name__)


def _wildcard_types(item: Dict[str, Any]) -> Optional[List[str]]:
    wt = item.get("wildcard_types")
    if wt is None:
        wt = item.get("wildcard_type")
    if wt is None:
        return None
    if isinstance(wt, list):
        return [str(x) for x in wt if x is not None]
    return [str(wt)]


def _merge_subdomain_row(
    program_id: uuid.UUID,
    apex_id: uuid.UUID,
    item: Dict[str, Any],
    existing: Optional[Subdomain],
    now_naive: datetime,
) -> Dict[str, Any]:
    """Build ORM row dict for insert/upsert matching create_or_update_subdomain merge rules."""
    name = item.get("name")
    if existing is None:
        wt = _wildcard_types(item)
        return {
            "id": uuid.uuid4(),
            "name": name,
            "apex_domain_id": apex_id,
            "program_id": program_id,
            "cname_record": item.get("cname_record"),
            "is_wildcard": bool(item.get("is_wildcard", False)),
            "wildcard_types": wt,
            "notes": item.get("notes"),
            "created_at": now_naive,
            "updated_at": now_naive,
        }

    meaningful = False
    cname = existing.cname_record
    if "cname_record" in item and item.get("cname_record") != existing.cname_record:
        cname = item.get("cname_record")
        meaningful = True

    is_wc = existing.is_wildcard
    if "is_wildcard" in item and item.get("is_wildcard") != existing.is_wildcard:
        is_wc = bool(item.get("is_wildcard"))
        meaningful = True

    wt = existing.wildcard_types
    provided_wt = _wildcard_types(item)
    if provided_wt is not None and provided_wt != (list(existing.wildcard_types or [])):
        wt = provided_wt
        meaningful = True

    notes = existing.notes
    if item.get("notes") and item.get("notes") != existing.notes:
        notes = item.get("notes")
        meaningful = True

    apex_changed_only = existing.apex_domain_id != apex_id and not meaningful
    new_apex = apex_id

    updated_at = existing.updated_at
    if meaningful:
        updated_at = now_naive

    return {
        "id": existing.id,
        "name": name,
        "apex_domain_id": new_apex,
        "program_id": program_id,
        "cname_record": cname,
        "is_wildcard": is_wc,
        "wildcard_types": wt,
        "notes": notes,
        "created_at": existing.created_at,
        "updated_at": updated_at,
        "_meaningful": meaningful,
        "_apex_changed_only": apex_changed_only,
    }


def upsert_subdomains_chunk(program_name: str, items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Process one chunk synchronously inside a worker thread.

    Returns partial counters and event payload lists for aggregation.
    """
    t0 = time.perf_counter()
    session = BatchSessionLocal()
    success_count = failed_count = 0
    created_count = updated_count = skipped_count = out_of_scope_count = 0
    created_assets: List[Dict] = []
    updated_assets: List[Dict] = []
    skipped_assets: List[Dict] = []
    implicit_apex_created_events: List[Dict] = []

    try:
        program = session.execute(
            select(Program).where(Program.name == program_name)
        ).scalar_one_or_none()
        if not program:
            raise ValueError(f"Program {program_name!r} not found")

        domain_regex = program.domain_regex or []
        oos_regex = program.out_of_scope_regex or []

        prepared_map: Dict[str, Tuple[Dict[str, Any], str, str]] = {}
        for raw in items:
            item = dict(raw)
            if not item.get("program_name"):
                item["program_name"] = program_name
            hostname = item.get("name")
            if not hostname:
                failed_count += 1
                skipped_assets.append(
                    {
                        "name": "unknown",
                        "program_name": program_name,
                        "error": "missing_name",
                    }
                )
                continue
            try:
                apex_name = item.get("apex_domain") or extract_apex_domain(hostname)
            except ValueError:
                failed_count += 1
                skipped_assets.append(
                    {
                        "name": hostname,
                        "program_name": program_name,
                        "error": "invalid_domain",
                    }
                )
                continue

            if not domain_in_scope(hostname, list(domain_regex), list(oos_regex)):
                out_of_scope_count += 1
                skipped_assets.append(
                    {
                        "name": hostname,
                        "program_name": program_name,
                        "reason": "out_of_scope",
                    }
                )
                continue

            prepared_map[hostname] = (item, hostname, apex_name)

        prepared = list(prepared_map.values())

        if not prepared:
            session.commit()
            return _pack(
                success_count,
                failed_count,
                created_count,
                updated_count,
                skipped_count,
                out_of_scope_count,
                created_assets,
                updated_assets,
                skipped_assets,
                implicit_apex_created_events,
                t0,
            )

        distinct_apex = sorted({p[2] for p in prepared})
        now_naive = datetime.now(timezone.utc).replace(tzinfo=None)

        apex_tbl = ApexDomain.__table__
        apex_insert = (
            insert(apex_tbl)
            .values(
                [
                    {
                        "id": uuid.uuid4(),
                        "name": nm,
                        "program_id": program.id,
                        "notes": None,
                        "created_at": now_naive,
                        "updated_at": now_naive,
                    }
                    for nm in distinct_apex
                ]
            )
            .on_conflict_do_nothing(
                index_elements=[apex_tbl.c.name, apex_tbl.c.program_id],
            )
            .returning(apex_tbl.c.id, apex_tbl.c.name)
        )
        inserted_apex = session.execute(apex_insert).all()
        for row in inserted_apex:
            implicit_apex_created_events.append(
                {
                    "event": "asset.created",
                    "asset_type": "apex_domain",
                    "record_id": str(row.id),
                    "name": row.name,
                    "program_name": program_name,
                    "notes": None,
                    "whois_status": None,
                }
            )

        apex_rows = session.execute(
            select(ApexDomain.id, ApexDomain.name).where(
                ApexDomain.program_id == program.id,
                ApexDomain.name.in_(distinct_apex),
            )
        ).all()
        apex_by_name = {r.name: r.id for r in apex_rows}

        names = [p[1] for p in prepared]
        existing_rows = session.execute(
            select(Subdomain).where(
                Subdomain.program_id == program.id,
                Subdomain.name.in_(names),
            )
        ).scalars().all()
        existing_by_name = {r.name: r for r in existing_rows}

        rows_out: List[Dict[str, Any]] = []
        meta: List[Dict[str, Any]] = []

        for item, hostname, apex_name in prepared:
            aid = apex_by_name.get(apex_name)
            if not aid:
                failed_count += 1
                skipped_assets.append(
                    {
                        "name": hostname,
                        "program_name": program_name,
                        "error": "apex_resolution_failed",
                    }
                )
                continue

            ex = existing_by_name.get(hostname)
            merged = _merge_subdomain_row(program.id, aid, item, ex, now_naive)
            meaningful = bool(merged.pop("_meaningful", False))
            apex_only = bool(merged.pop("_apex_changed_only", False))

            rows_out.append(merged)
            meta.append(
                {
                    "item": item,
                    "hostname": hostname,
                    "had_existing": ex is not None,
                    "meaningful": meaningful,
                    "apex_only": apex_only,
                }
            )

        if not rows_out:
            session.commit()
            return _pack(
                success_count,
                failed_count,
                created_count,
                updated_count,
                skipped_count,
                out_of_scope_count,
                created_assets,
                updated_assets,
                skipped_assets,
                implicit_apex_created_events,
                t0,
            )

        sub_tbl = Subdomain.__table__
        ins = insert(sub_tbl).values(rows_out)
        ex = ins.excluded
        ins = (
            ins.on_conflict_do_update(
                index_elements=[sub_tbl.c.name, sub_tbl.c.program_id],
                set_={
                    "apex_domain_id": ex.apex_domain_id,
                    "cname_record": ex.cname_record,
                    "is_wildcard": ex.is_wildcard,
                    "wildcard_types": ex.wildcard_types,
                    "notes": ex.notes,
                    "updated_at": ex.updated_at,
                },
            )
            .returning(
                sub_tbl.c.id,
                sub_tbl.c.name,
                sub_tbl.c.created_at,
                sub_tbl.c.updated_at,
            )
        )
        returned = session.execute(ins).all()

        id_by_name = {r.name: r.id for r in returned}
        created_at_by_name = {r.name: r.created_at for r in returned}
        updated_at_by_name = {r.name: r.updated_at for r in returned}

        for m in meta:
            item = m["item"]
            hostname = m["hostname"]
            sid = id_by_name.get(hostname)
            if not sid:
                failed_count += 1
                continue

            apex_label = item.get("apex_domain") or extract_apex_domain(hostname)
            base_event = {
                "name": hostname,
                "program_name": program_name,
                "apex_domain": apex_label,
                "ip": item.get("ip", []),
                "cname_record": item.get("cname_record"),
                "is_wildcard": item.get("is_wildcard"),
            }

            if not m["had_existing"]:
                created_count += 1
                success_count += 1
                created_assets.append(
                    {
                        "event": "asset.created",
                        "asset_type": "subdomain",
                        "record_id": str(sid),
                        **base_event,
                        "previous_ip_count": 0,
                        "new_ip_count": len(item.get("ip", []) or [])
                        if isinstance(item.get("ip"), list)
                        else 0,
                        "resolution_status": (
                            "created_resolved"
                            if item.get("ip") and isinstance(item["ip"], list) and len(item["ip"]) > 0
                            else None
                        ),
                    }
                )
            elif m["meaningful"]:
                updated_count += 1
                success_count += 1
                ex = existing_by_name.get(hostname)
                prev_ip = 0
                if ex:
                    prev_ip = len(
                        session.scalars(
                            select(SubdomainIP).where(SubdomainIP.subdomain_id == ex.id)
                        ).all()
                    )
                new_ip = len(
                    session.scalars(
                        select(SubdomainIP).where(SubdomainIP.subdomain_id == sid)
                    ).all()
                )
                updated_assets.append(
                    {
                        "event": "asset.updated",
                        "asset_type": "subdomain",
                        "record_id": str(sid),
                        **base_event,
                        "previous_ip_count": prev_ip,
                        "new_ip_count": new_ip,
                        "resolution_status": None,
                    }
                )
            elif m["apex_only"]:
                skipped_count += 1
                success_count += 1
                skipped_assets.append(
                    {
                        "record_id": str(sid),
                        "name": hostname,
                        "program_name": program_name,
                        "reason": "duplicate",
                    }
                )
            else:
                skipped_count += 1
                success_count += 1
                skipped_assets.append(
                    {
                        "record_id": str(sid),
                        "name": hostname,
                        "program_name": program_name,
                        "reason": "duplicate",
                    }
                )

        _bulk_link_subdomain_ips(session, program.id, prepared, id_by_name, now_naive)

        # Refresh IP counts on events after junction inserts
        for ev in created_assets:
            if ev.get("asset_type") == "subdomain" and ev.get("record_id"):
                sid = uuid.UUID(ev["record_id"])
                ev["new_ip_count"] = len(
                    session.scalars(
                        select(SubdomainIP).where(SubdomainIP.subdomain_id == sid)
                    ).all()
                )
        for ev in updated_assets:
            if ev.get("asset_type") == "subdomain" and ev.get("record_id"):
                sid = uuid.UUID(ev["record_id"])
                ev["new_ip_count"] = len(
                    session.scalars(
                        select(SubdomainIP).where(SubdomainIP.subdomain_id == sid)
                    ).all()
                )

        session.commit()
    except Exception:
        session.rollback()
        logger.exception("bulk_sql subdomains chunk failed")
        raise
    finally:
        session.close()

    dt = time.perf_counter() - t0
    logger.info(
        "bulk_sql subdomains chunk: program=%s items=%s wall_ms=%.1f created=%s updated=%s skipped=%s oos=%s failed=%s",
        program_name,
        len(items),
        dt * 1000,
        created_count,
        updated_count,
        skipped_count,
        out_of_scope_count,
        failed_count,
    )

    return _pack(
        success_count,
        failed_count,
        created_count,
        updated_count,
        skipped_count,
        out_of_scope_count,
        created_assets,
        updated_assets,
        skipped_assets,
        implicit_apex_created_events,
        t0,
    )


def _pack(
    success_count: int,
    failed_count: int,
    created_count: int,
    updated_count: int,
    skipped_count: int,
    out_of_scope_count: int,
    created_assets: List[Dict],
    updated_assets: List[Dict],
    skipped_assets: List[Dict],
    implicit_apex_created_events: List[Dict],
    t0: float,
) -> Dict[str, Any]:
    return {
        "success_count": success_count,
        "failed_count": failed_count,
        "created_count": created_count,
        "updated_count": updated_count,
        "skipped_count": skipped_count,
        "out_of_scope_count": out_of_scope_count,
        "created_assets": created_assets,
        "updated_assets": updated_assets,
        "skipped_assets": skipped_assets,
        "implicit_apex_created_events": implicit_apex_created_events,
        "t0": t0,
    }


def _bulk_link_subdomain_ips(
    session,
    program_id: uuid.UUID,
    prepared: List[Tuple[Dict[str, Any], str, str]],
    id_by_name: Dict[str, uuid.UUID],
    now_naive: datetime,
) -> None:
    """Insert missing IPs and subdomain_ips rows (parity with create_or_update_subdomain)."""
    ip_pairs: List[Tuple[str, uuid.UUID]] = []
    for item, hostname, _apex in prepared:
        sid = id_by_name.get(hostname)
        if not sid or "ip" not in item or not isinstance(item["ip"], list):
            continue
        for ip_address in item["ip"]:
            if isinstance(ip_address, str) and ip_address.strip():
                ip_pairs.append((ip_address.strip(), sid))

    if not ip_pairs:
        return

    distinct_addrs = sorted({p[0] for p in ip_pairs})
    ip_values = [
        {
            "id": uuid.uuid4(),
            "ip_address": addr,
            "ptr_record": None,
            "service_provider": None,
            "program_id": program_id,
            "notes": None,
            "created_at": now_naive,
            "updated_at": now_naive,
        }
        for addr in distinct_addrs
    ]
    ip_tbl = IP.__table__
    ii = insert(ip_tbl).values(ip_values).on_conflict_do_nothing(
        index_elements=[ip_tbl.c.ip_address, ip_tbl.c.program_id],
    )
    session.execute(ii)

    ip_rows = session.execute(
        select(IP.id, IP.ip_address).where(
            IP.program_id == program_id,
            IP.ip_address.in_(distinct_addrs),
        )
    ).all()
    ip_id_by_addr = {str(r.ip_address): r.id for r in ip_rows}

    si_values = []
    for addr, sub_id in ip_pairs:
        iid = ip_id_by_addr.get(addr)
        if not iid:
            continue
        si_values.append(
            {
                "id": uuid.uuid4(),
                "subdomain_id": sub_id,
                "ip_id": iid,
                "created_at": now_naive,
            }
        )
    if si_values:
        si_tbl = SubdomainIP.__table__
        si = insert(si_tbl).values(si_values).on_conflict_do_nothing(
            index_elements=[si_tbl.c.subdomain_id, si_tbl.c.ip_id],
        )
        session.execute(si)


async def bulk_create_or_update_subdomains_all(
    subdomains: List[Dict[str, Any]],
    program_name: str,
) -> Tuple[int, int, int, int, int, List[Dict], List[Dict], List[Dict], List[Dict]]:
    """Split into SQL chunks and run each in a worker thread."""
    import asyncio

    chunk_sz = sql_chunk_size()
    success_count = 0
    failed_count = 0
    created_count = 0
    updated_count = 0
    skipped_count = 0
    out_of_scope_count = 0
    created_assets: List[Dict] = []
    updated_assets: List[Dict] = []
    skipped_assets: List[Dict] = []
    implicit_apex_created_events: List[Dict] = []

    for i in range(0, len(subdomains), chunk_sz):
        chunk = subdomains[i : i + chunk_sz]
        part = await asyncio.to_thread(upsert_subdomains_chunk, program_name, chunk)
        success_count += part["success_count"]
        failed_count += part["failed_count"]
        created_count += part["created_count"]
        updated_count += part["updated_count"]
        skipped_count += part["skipped_count"]
        out_of_scope_count += part["out_of_scope_count"]
        created_assets.extend(part["created_assets"])
        updated_assets.extend(part["updated_assets"])
        skipped_assets.extend(part["skipped_assets"])
        implicit_apex_created_events.extend(part["implicit_apex_created_events"])
        await asyncio.sleep(0)

    logger.info(
        "bulk_sql subdomains total: program=%s rows=%s success=%s failed=%s created=%s updated=%s skipped=%s oos=%s",
        program_name,
        len(subdomains),
        success_count,
        failed_count,
        created_count,
        updated_count,
        skipped_count,
        out_of_scope_count,
    )

    return (
        success_count,
        failed_count,
        created_count,
        updated_count,
        skipped_count + out_of_scope_count,
        created_assets,
        updated_assets,
        skipped_assets,
        implicit_apex_created_events,
    )
