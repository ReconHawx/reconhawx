"""Chunked bulk upsert for services (PostgreSQL)."""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from db import BatchSessionLocal
from models.postgres import IP, Program, Service
from repository.bulk_sql.config import sql_chunk_size

logger = logging.getLogger(__name__)


def upsert_services_chunk(program_name: str, items: List[Dict[str, Any]]) -> Dict[str, Any]:
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

        now_naive = datetime.now(timezone.utc).replace(tzinfo=None)

        dedup: Dict[Tuple[str, int], Dict[str, Any]] = {}
        order: List[Tuple[str, int]] = []
        for raw in items:
            item = dict(raw)
            if not item.get("program_name"):
                item["program_name"] = program_name
            ip_s = item.get("ip")
            port = item.get("port")
            if ip_s is None or port is None:
                failed_count += 1
                skipped_assets.append(
                    {
                        "ip": str(ip_s),
                        "port": str(port),
                        "program_name": program_name,
                        "error": "missing_ip_or_port",
                    }
                )
                continue
            try:
                port_i = int(port)
            except (TypeError, ValueError):
                failed_count += 1
                skipped_assets.append(
                    {
                        "ip": str(ip_s),
                        "port": str(port),
                        "program_name": program_name,
                        "error": "invalid_port",
                    }
                )
                continue
            key = (str(ip_s), port_i)
            if key not in dedup:
                order.append(key)
            dedup[key] = item

        if not order:
            session.commit()
            return _pack(
                success_count,
                failed_count,
                created_count,
                updated_count,
                skipped_count,
                created_assets,
                updated_assets,
                skipped_assets,
                t0,
            )

        distinct_ips = sorted({k[0] for k in order})
        ip_tbl = IP.__table__
        ip_rows = [
            {
                "id": uuid.uuid4(),
                "ip_address": addr,
                "ptr_record": None,
                "service_provider": None,
                "program_id": program.id,
                "notes": None,
                "created_at": now_naive,
                "updated_at": now_naive,
            }
            for addr in distinct_ips
        ]
        if ip_rows:
            session.execute(
                insert(ip_tbl)
                .values(ip_rows)
                .on_conflict_do_nothing(
                    index_elements=[ip_tbl.c.ip_address, ip_tbl.c.program_id],
                )
            )

        ip_db = session.execute(
            select(IP.id, IP.ip_address).where(
                IP.program_id == program.id,
                IP.ip_address.in_(distinct_ips),
            )
        ).all()
        ip_id_by_addr = {str(r.ip_address): r.id for r in ip_db}

        svc_tbl = Service.__table__
        rows_to_upsert: List[Dict[str, Any]] = []
        meta: List[Dict[str, Any]] = []

        for ip_s, port_i in order:
            item = dedup[(ip_s, port_i)]
            iid = ip_id_by_addr.get(ip_s)
            if not iid:
                failed_count += 1
                skipped_assets.append(
                    {
                        "ip": ip_s,
                        "port": port_i,
                        "program_name": program_name,
                        "error": "ip_resolution_failed",
                    }
                )
                continue

            existing = session.execute(
                select(Service).where(
                    Service.ip_id == iid,
                    Service.port == port_i,
                    Service.program_id == program.id,
                )
            ).scalar_one_or_none()

            meaningful = False
            if existing:
                sn = existing.service_name
                pr = existing.protocol
                bn = existing.banner
                nt = existing.notes
                nv = existing.nerva_metadata
                if "service_name" in item and item.get("service_name") is not None and item.get("service_name") != sn:
                    sn = item.get("service_name")
                    meaningful = True
                if "protocol" in item and item.get("protocol") is not None and item.get("protocol") != pr:
                    pr = item.get("protocol")
                    meaningful = True
                if "banner" in item and item.get("banner") is not None and item.get("banner") != bn:
                    bn = item.get("banner")
                    meaningful = True
                if "notes" in item and item.get("notes") is not None and item.get("notes") != nt:
                    nt = item.get("notes")
                    meaningful = True
                if "nerva_metadata" in item and item.get("nerva_metadata") is not None and item.get("nerva_metadata") != nv:
                    nv = item.get("nerva_metadata")
                    meaningful = True
                updated_at = now_naive if meaningful else existing.updated_at
                rows_to_upsert.append(
                    {
                        "id": existing.id,
                        "ip_id": iid,
                        "port": port_i,
                        "protocol": pr,
                        "service_name": sn or "",
                        "banner": bn,
                        "program_id": program.id,
                        "notes": nt,
                        "nerva_metadata": nv,
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
                        "ip_id": iid,
                        "port": port_i,
                        "protocol": item.get("protocol", "tcp"),
                        "service_name": item.get("service_name", "") or "",
                        "banner": item.get("banner"),
                        "program_id": program.id,
                        "notes": item.get("notes"),
                        "nerva_metadata": item.get("nerva_metadata"),
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
                created_assets,
                updated_assets,
                skipped_assets,
                t0,
            )

        ins = insert(svc_tbl).values(rows_to_upsert)
        ex = ins.excluded
        ins = ins.on_conflict_do_update(
            index_elements=[svc_tbl.c.ip_id, svc_tbl.c.port, svc_tbl.c.program_id],
            set_={
                "protocol": ex.protocol,
                "service_name": ex.service_name,
                "banner": ex.banner,
                "notes": ex.notes,
                "nerva_metadata": ex.nerva_metadata,
                "updated_at": ex.updated_at,
            },
        ).returning(svc_tbl.c.id, svc_tbl.c.ip_id, svc_tbl.c.port)
        ret = session.execute(ins).all()
        id_by_key = {(r.ip_id, int(r.port)): r.id for r in ret}

        for m in meta:
            item = m["item"]
            ip_s = str(item["ip"])
            port_i = int(item["port"])
            iid = ip_id_by_addr.get(ip_s)
            if not iid:
                continue
            sid = id_by_key.get((iid, port_i))
            if not sid:
                failed_count += 1
                continue
            success_count += 1
            if m["action"] == "created":
                created_count += 1
                created_assets.append(
                    {
                        "event": "asset.created",
                        "asset_type": "service",
                        "record_id": str(sid),
                        "ip": item.get("ip"),
                        "port": item.get("port"),
                        "program_name": program_name,
                        "service_name": item.get("service_name"),
                        "protocol": item.get("protocol", "tcp"),
                        "banner": item.get("banner"),
                    }
                )
            elif m["action"] == "updated" and m["meaningful"]:
                updated_count += 1
                updated_assets.append(
                    {
                        "event": "asset.updated",
                        "asset_type": "service",
                        "record_id": str(sid),
                        "ip": item.get("ip"),
                        "port": item.get("port"),
                        "program_name": program_name,
                        "service_name": item.get("service_name"),
                        "protocol": item.get("protocol", "tcp"),
                        "banner": item.get("banner"),
                    }
                )
            else:
                skipped_count += 1
                skipped_assets.append(
                    {
                        "record_id": str(sid),
                        "ip": item.get("ip"),
                        "port": item.get("port"),
                        "program_name": program_name,
                        "reason": "duplicate",
                    }
                )

        session.commit()
    except Exception:
        session.rollback()
        logger.exception("bulk_sql services chunk failed")
        raise
    finally:
        session.close()

    logger.info(
        "bulk_sql services chunk program=%s items=%s created=%s updated=%s skipped=%s wall_ms=%.1f",
        program_name,
        len(items),
        created_count,
        updated_count,
        skipped_count,
        (time.perf_counter() - t0) * 1000,
    )
    return _pack(
        success_count,
        failed_count,
        created_count,
        updated_count,
        skipped_count,
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
        "created_assets": created_assets,
        "updated_assets": updated_assets,
        "skipped_assets": skipped_assets,
        "t0": t0,
    }


async def bulk_create_or_update_services_all(
    services: List[Dict[str, Any]],
    program_name: str,
) -> Tuple[int, int, int, int, int, List[Dict], List[Dict], List[Dict]]:
    import asyncio

    chunk_sz = sql_chunk_size()
    sc = fc = cc = uc = sk = 0
    ca: List[Dict] = []
    ua: List[Dict] = []
    sa: List[Dict] = []
    for i in range(0, len(services), chunk_sz):
        p = await asyncio.to_thread(upsert_services_chunk, program_name, services[i : i + chunk_sz])
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
