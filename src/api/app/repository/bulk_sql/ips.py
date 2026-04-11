"""Chunked bulk upsert for IPs."""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from db import BatchSessionLocal
from models.postgres import IP, Program
from repository.bulk_sql.config import sql_chunk_size
from repository.bulk_sql.scope import domain_in_scope

logger = logging.getLogger(__name__)


def upsert_ips_chunk(program_name: str, items: List[Dict[str, Any]]) -> Dict[str, Any]:
    session = BatchSessionLocal()
    success_count = failed_count = 0
    created_count = updated_count = skipped_count = out_of_scope_count = 0
    created_assets: List[Dict] = []
    updated_assets: List[Dict] = []
    skipped_assets: List[Dict] = []
    t0 = time.perf_counter()

    try:
        program = session.execute(
            select(Program).where(Program.name == program_name)
        ).scalar_one_or_none()
        if not program:
            raise ValueError(f"Program {program_name!r} not found")

        now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
        domain_regex = program.domain_regex or []
        oos_regex = program.out_of_scope_regex or []

        dedup: Dict[str, Dict[str, Any]] = {}
        order: List[str] = []
        for raw in items:
            item = dict(raw)
            if not item.get("program_name"):
                item["program_name"] = program_name
            addr = item.get("ip")
            if not addr:
                failed_count += 1
                skipped_assets.append(
                    {
                        "ip_address": "unknown",
                        "program_name": program_name,
                        "error": "missing_ip",
                    }
                )
                continue
            saddr = str(addr)
            if saddr not in dedup:
                order.append(saddr)
            dedup[saddr] = item

        rows_to_upsert: List[Dict[str, Any]] = []
        meta: List[Dict[str, Any]] = []

        for saddr in order:
            item = dedup[saddr]
            disco = item.get("discovered_via_domain")
            if disco and not domain_in_scope(disco, list(domain_regex), list(oos_regex)):
                out_of_scope_count += 1
                skipped_assets.append(
                    {
                        "ip_address": saddr,
                        "program_name": program_name,
                        "reason": "out_of_scope",
                    }
                )
                continue

            existing = session.execute(
                select(IP).where(
                    IP.ip_address == saddr,
                    IP.program_id == program.id,
                )
            ).scalar_one_or_none()

            meaningful = False
            if existing:
                ptr = existing.ptr_record
                if item.get("ptr") and item.get("ptr") != existing.ptr_record:
                    ptr = item.get("ptr")
                    meaningful = True
                sp = existing.service_provider
                if item.get("service_provider") and item.get("service_provider") != existing.service_provider:
                    sp = item.get("service_provider")
                    meaningful = True
                notes = existing.notes
                if item.get("notes") and item.get("notes") != existing.notes:
                    notes = item.get("notes")
                    meaningful = True
                updated_at = now_naive if meaningful else existing.updated_at
                rows_to_upsert.append(
                    {
                        "id": existing.id,
                        "ip_address": saddr,
                        "ptr_record": ptr,
                        "service_provider": sp,
                        "program_id": program.id,
                        "notes": notes,
                        "created_at": existing.created_at,
                        "updated_at": updated_at,
                    }
                )
                meta.append(
                    {
                        "item": item,
                        "action": "updated" if meaningful else "skipped",
                        "meaningful": meaningful,
                    }
                )
            else:
                rows_to_upsert.append(
                    {
                        "id": uuid.uuid4(),
                        "ip_address": saddr,
                        "ptr_record": item.get("ptr"),
                        "service_provider": item.get("service_provider"),
                        "program_id": program.id,
                        "notes": item.get("notes"),
                        "created_at": now_naive,
                        "updated_at": now_naive,
                    }
                )
                meta.append({"item": item, "action": "created", "meaningful": True})

        if not rows_to_upsert:
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
                t0,
            )

        tbl = IP.__table__
        ins = insert(tbl).values(rows_to_upsert)
        ex = ins.excluded
        ins = ins.on_conflict_do_update(
            index_elements=[tbl.c.ip_address, tbl.c.program_id],
            set_={
                "ptr_record": ex.ptr_record,
                "service_provider": ex.service_provider,
                "notes": ex.notes,
                "updated_at": ex.updated_at,
            },
        ).returning(tbl.c.id, tbl.c.ip_address)
        ret = session.execute(ins).all()

        id_by_addr = {str(r.ip_address): r.id for r in ret}

        for m in meta:
            item = m["item"]
            addr = str(item["ip"])
            iid = id_by_addr.get(addr)
            if not iid:
                failed_count += 1
                continue
            success_count += 1
            if m["action"] == "created":
                created_count += 1
                created_assets.append(
                    {
                        "event": "asset.created",
                        "asset_type": "ip",
                        "record_id": str(iid),
                        "ip_address": addr,
                        "program_name": program_name,
                        "ptr_record": item.get("ptr"),
                        "service_provider": item.get("service_provider"),
                        "notes": item.get("notes"),
                    }
                )
            elif m["action"] == "updated" and m["meaningful"]:
                updated_count += 1
                updated_assets.append(
                    {
                        "event": "asset.updated",
                        "asset_type": "ip",
                        "record_id": str(iid),
                        "ip_address": addr,
                        "program_name": program_name,
                        "ptr_record": item.get("ptr"),
                        "service_provider": item.get("service_provider"),
                        "notes": item.get("notes"),
                    }
                )
            else:
                skipped_count += 1
                skipped_assets.append(
                    {
                        "record_id": str(iid),
                        "ip_address": addr,
                        "program_name": program_name,
                        "reason": "duplicate",
                    }
                )

        session.commit()
    except Exception:
        session.rollback()
        logger.exception("bulk_sql ips chunk failed")
        raise
    finally:
        session.close()

    logger.info(
        "bulk_sql ips chunk program=%s items=%s created=%s updated=%s skipped=%s oos=%s wall_ms=%.1f",
        program_name,
        len(items),
        created_count,
        updated_count,
        skipped_count,
        out_of_scope_count,
        (time.perf_counter() - t0) * 1000,
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
        "t0": t0,
    }


async def bulk_create_or_update_ips_all(
    ips: List[Dict[str, Any]],
    program_name: str,
) -> Tuple[int, int, int, int, int, List[Dict], List[Dict], List[Dict]]:
    import asyncio

    chunk_sz = sql_chunk_size()
    agg = _empty_ip_agg()
    for i in range(0, len(ips), chunk_sz):
        part = await asyncio.to_thread(upsert_ips_chunk, program_name, ips[i : i + chunk_sz])
        _merge_ip_agg(agg, part)
        await asyncio.sleep(0)
    return (
        agg["success_count"],
        agg["failed_count"],
        agg["created_count"],
        agg["updated_count"],
        agg["skipped_count"] + agg["out_of_scope_count"],
        agg["created_assets"],
        agg["updated_assets"],
        agg["skipped_assets"],
    )


def _empty_ip_agg() -> Dict[str, Any]:
    return {
        "success_count": 0,
        "failed_count": 0,
        "created_count": 0,
        "updated_count": 0,
        "skipped_count": 0,
        "out_of_scope_count": 0,
        "created_assets": [],
        "updated_assets": [],
        "skipped_assets": [],
    }


def _merge_ip_agg(agg: Dict[str, Any], part: Dict[str, Any]) -> None:
    agg["success_count"] += part["success_count"]
    agg["failed_count"] += part["failed_count"]
    agg["created_count"] += part["created_count"]
    agg["updated_count"] += part["updated_count"]
    agg["skipped_count"] += part["skipped_count"]
    agg["out_of_scope_count"] += part["out_of_scope_count"]
    agg["created_assets"].extend(part["created_assets"])
    agg["updated_assets"].extend(part["updated_assets"])
    agg["skipped_assets"].extend(part["skipped_assets"])
