"""Chunked bulk upsert for apex domains (single transaction per chunk, ORM merge)."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from sqlalchemy import select

from db import BatchSessionLocal
from models.postgres import ApexDomain, Program
from repository.apexdomain_assets_repo import WHOIS_COLUMNS, _apply_whois_from_payload
from repository.bulk_sql.config import sql_chunk_size
from repository.bulk_sql.scope import domain_in_scope

logger = logging.getLogger(__name__)


def upsert_apex_domains_chunk(program_name: str, items: List[Dict[str, Any]]) -> Dict[str, Any]:
    session = BatchSessionLocal()
    success_count = failed_count = 0
    created_count = updated_count = skipped_count = 0
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

        domain_regex = program.domain_regex or []
        oos_regex = program.out_of_scope_regex or []
        now_naive = datetime.now(timezone.utc).replace(tzinfo=None)

        dedup: Dict[str, Dict[str, Any]] = {}
        order: List[str] = []
        for raw in items:
            item = dict(raw)
            if not item.get("program_name"):
                item["program_name"] = program_name
            nm = item.get("name")
            if not nm:
                failed_count += 1
                skipped_assets.append(
                    {"name": "unknown", "program_name": program_name, "error": "missing_name"}
                )
                continue
            if nm not in dedup:
                order.append(nm)
            dedup[nm] = item

        names = list(order)
        existing_rows = (
            session.execute(
                select(ApexDomain).where(
                    ApexDomain.program_id == program.id,
                    ApexDomain.name.in_(names),
                )
            ).scalars().all()
            if names
            else []
        )
        by_name = {r.name: r for r in existing_rows}

        for nm in order:
            item = dedup[nm]
            ex = by_name.get(nm)
            if ex is None:
                if not domain_in_scope(nm, list(domain_regex), list(oos_regex)):
                    failed_count += 1
                    skipped_assets.append(
                        {
                            "name": nm,
                            "program_name": program_name,
                            "error": "out_of_scope",
                        }
                    )
                    continue
                ad = ApexDomain(
                    name=nm,
                    program_id=program.id,
                    notes=item.get("notes"),
                    created_at=now_naive,
                    updated_at=now_naive,
                )
                has_whois_payload = any(
                    k in item for k in WHOIS_COLUMNS if k != "whois_checked_at"
                )
                if has_whois_payload:
                    _apply_whois_from_payload(ad, item)
                    ad.whois_checked_at = now_naive
                session.add(ad)
                session.flush()
                created_count += 1
                success_count += 1
                created_assets.append(
                    {
                        "event": "asset.created",
                        "asset_type": "apex_domain",
                        "record_id": str(ad.id),
                        "name": nm,
                        "program_name": program_name,
                        "notes": item.get("notes"),
                        "whois_status": item.get("whois_status"),
                    }
                )
                by_name[nm] = ad
            else:
                updated = False
                if item.get("notes") is not None and item.get("notes") != ex.notes:
                    ex.notes = item.get("notes")
                    updated = True
                has_whois_payload = any(
                    k in item for k in WHOIS_COLUMNS if k != "whois_checked_at"
                )
                if has_whois_payload:
                    if _apply_whois_from_payload(ex, item):
                        updated = True
                    ex.whois_checked_at = now_naive
                    updated = True
                if updated:
                    ex.updated_at = now_naive
                    updated_count += 1
                    success_count += 1
                    updated_assets.append(
                        {
                            "event": "asset.updated",
                            "asset_type": "apex_domain",
                            "record_id": str(ex.id),
                            "name": nm,
                            "program_name": program_name,
                            "notes": item.get("notes"),
                            "whois_status": item.get("whois_status"),
                        }
                    )
                else:
                    skipped_count += 1
                    success_count += 1
                    skipped_assets.append(
                        {
                            "record_id": str(ex.id),
                            "name": nm,
                            "program_name": program_name,
                            "reason": "duplicate",
                        }
                    )

        session.commit()
    except Exception:
        session.rollback()
        logger.exception("bulk_sql apex_domains chunk failed")
        raise
    finally:
        session.close()

    logger.info(
        "bulk_sql apex chunk program=%s items=%s created=%s updated=%s skipped=%s wall_ms=%.1f",
        program_name,
        len(items),
        created_count,
        updated_count,
        skipped_count,
        (time.perf_counter() - t0) * 1000,
    )
    return {
        "success_count": success_count,
        "failed_count": failed_count,
        "created_count": created_count,
        "updated_count": updated_count,
        "skipped_count": skipped_count,
        "created_assets": created_assets,
        "updated_assets": updated_assets,
        "skipped_assets": skipped_assets,
        "t0": t0,
    }


async def bulk_create_or_update_apex_domains_all(
    apex_domains: List[Dict[str, Any]],
    program_name: str,
) -> Tuple[int, int, int, int, int, List[Dict], List[Dict], List[Dict]]:
    import asyncio

    chunk_sz = sql_chunk_size()
    sc = fc = cc = uc = sk = 0
    ca: List[Dict] = []
    ua: List[Dict] = []
    sa: List[Dict] = []
    for i in range(0, len(apex_domains), chunk_sz):
        p = await asyncio.to_thread(upsert_apex_domains_chunk, program_name, apex_domains[i : i + chunk_sz])
        sc += p["success_count"]
        fc += p["failed_count"]
        cc += p["created_count"]
        uc += p["updated_count"]
        sk += p["skipped_count"]
        ca.extend(p["created_assets"])
        ua.extend(p["updated_assets"])
        sa.extend(p["skipped_assets"])
        await asyncio.sleep(0)
    return sc, fc, cc, uc, sk, ca, ua, sa
