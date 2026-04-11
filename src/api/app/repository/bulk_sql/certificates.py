"""Chunked bulk upsert for certificates (PostgreSQL)."""

from __future__ import annotations

import hashlib
import logging
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from db import BatchSessionLocal
from models.postgres import Certificate, Program
from repository.bulk_sql.config import sql_chunk_size

logger = logging.getLogger(__name__)


def _subject_cn(cert: Dict[str, Any]) -> str:
    subject_cn = cert.get("subject_cn")
    if not subject_cn and cert.get("subject_dn"):
        cn_match = re.search(r"CN=([^,]+)", cert.get("subject_dn", ""))
        if cn_match:
            subject_cn = cn_match.group(1)
        else:
            subject_cn = (cert.get("subject_dn") or "")[:255]
    return subject_cn or ""


def _issuer_cn(cert: Dict[str, Any]) -> str:
    issuer_cn = cert.get("issuer_cn")
    if not issuer_cn and cert.get("issuer_dn"):
        cn_match = re.search(r"CN=([^,]+)", cert.get("issuer_dn", ""))
        if cn_match:
            issuer_cn = cn_match.group(1)
        else:
            issuer_cn = (cert.get("issuer_dn") or "")[:255]
    return issuer_cn or ""


def _serial(cert: Dict[str, Any]) -> str:
    s = cert.get("serial_number") or cert.get("serial")
    if not s:
        return str(uuid.uuid4())
    return str(s)


def _fingerprint(cert: Dict[str, Any], serial_number: str) -> str:
    fp = cert.get("fingerprint_hash")
    if fp:
        return str(fp)
    h = hashlib.sha256()
    h.update(f"{cert.get('subject_dn')}{serial_number}".encode())
    return h.hexdigest()


def _parse_dt(cert: Dict[str, Any], *keys: str) -> datetime:
    for k in keys:
        v = cert.get(k)
        if not v:
            continue
        if isinstance(v, datetime):
            dt = v
            if dt.tzinfo is not None:
                dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
            return dt
        if isinstance(v, str):
            s = v.strip()
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            try:
                dt = datetime.fromisoformat(s)
                if dt.tzinfo is not None:
                    dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
                return dt
            except ValueError:
                continue
    return datetime.utcnow()


def _merge_san(existing: Optional[List[str]], new: Optional[List[str]]) -> Optional[List[str]]:
    ex = list(existing or [])
    nw = list(new or [])
    merged = list(dict.fromkeys(ex + nw))
    return merged if merged else None


def upsert_certificates_chunk(program_name: str, items: List[Dict[str, Any]]) -> Dict[str, Any]:
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

        dedup: Dict[str, Dict[str, Any]] = {}
        order: List[str] = []
        for raw in items:
            item = dict(raw)
            if not item.get("program_name"):
                item["program_name"] = program_name
            if not item.get("subject_dn"):
                failed_count += 1
                skipped_assets.append(
                    {
                        "subject_dn": "unknown",
                        "program_name": program_name,
                        "error": "missing_subject_dn",
                    }
                )
                continue
            sn = _serial(item)
            if sn not in dedup:
                order.append(sn)
            dedup[sn] = item

        rows: List[Dict[str, Any]] = []
        meta: List[Dict[str, Any]] = []

        for serial in order:
            item = dedup[serial]
            existing = session.execute(
                select(Certificate).where(
                    Certificate.serial_number == serial,
                    Certificate.program_id == program.id,
                )
            ).scalar_one_or_none()

            subject_cn = _subject_cn(item)
            issuer_cn = _issuer_cn(item)
            valid_from = _parse_dt(item, "valid_from", "not_valid_before")
            valid_until = _parse_dt(item, "valid_until", "not_valid_after")
            san = item.get("subject_alternative_names") or item.get("subject_an") or []
            if not isinstance(san, list):
                san = [san] if san else []
            fp = _fingerprint(item, serial)

            meaningful = False
            if existing:
                row = {
                    "id": existing.id,
                    "subject_dn": item.get("subject_dn") if item.get("subject_dn") is not None else existing.subject_dn,
                    "subject_cn": subject_cn or existing.subject_cn,
                    "tls_version": item.get("tls_version", existing.tls_version),
                    "cipher": item.get("cipher", existing.cipher),
                    "subject_alternative_names": _merge_san(
                        list(existing.subject_alternative_names or []), san
                    ),
                    "valid_from": valid_from,
                    "valid_until": valid_until,
                    "issuer_dn": item.get("issuer_dn", existing.issuer_dn),
                    "issuer_cn": issuer_cn or existing.issuer_cn,
                    "issuer_organization": item.get("issuer_organization", existing.issuer_organization),
                    "serial_number": serial,
                    "fingerprint_hash": fp,
                    "program_id": program.id,
                    "notes": item.get("notes", existing.notes),
                    "created_at": existing.created_at,
                    "updated_at": existing.updated_at,
                }
                if row["subject_alternative_names"] != list(existing.subject_alternative_names or []):
                    meaningful = True
                simple = [
                    ("subject_cn", subject_cn),
                    ("tls_version", item.get("tls_version")),
                    ("cipher", item.get("cipher")),
                    ("notes", item.get("notes")),
                ]
                for field, val in simple:
                    if val is not None and val != getattr(existing, field):
                        meaningful = True
                for field in ("valid_from", "valid_until", "issuer_dn", "issuer_cn"):
                    if row[field] != getattr(existing, field):
                        meaningful = True
                if item.get("fingerprint_hash") and item.get("fingerprint_hash") != existing.fingerprint_hash:
                    meaningful = True
                row["updated_at"] = now_naive if meaningful else existing.updated_at
                rows.append(row)
                meta.append({"item": item, "action": "updated" if meaningful else "skipped", "serial": serial})
            else:
                rows.append(
                    {
                        "id": uuid.uuid4(),
                        "subject_dn": item.get("subject_dn"),
                        "subject_cn": subject_cn,
                        "tls_version": item.get("tls_version"),
                        "cipher": item.get("cipher"),
                        "subject_alternative_names": san or None,
                        "valid_from": valid_from,
                        "valid_until": valid_until,
                        "issuer_dn": item.get("issuer_dn"),
                        "issuer_cn": issuer_cn,
                        "issuer_organization": item.get("issuer_organization", []),
                        "serial_number": serial,
                        "fingerprint_hash": fp,
                        "program_id": program.id,
                        "notes": item.get("notes"),
                        "created_at": now_naive,
                        "updated_at": now_naive,
                    }
                )
                meta.append({"item": item, "action": "created", "serial": serial})

        if not rows:
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

        tbl = Certificate.__table__
        ins = insert(tbl).values(rows)
        ex = ins.excluded
        ins = ins.on_conflict_do_update(
            index_elements=[tbl.c.serial_number, tbl.c.program_id],
            set_={
                "subject_dn": ex.subject_dn,
                "subject_cn": ex.subject_cn,
                "tls_version": ex.tls_version,
                "cipher": ex.cipher,
                "subject_alternative_names": ex.subject_alternative_names,
                "valid_from": ex.valid_from,
                "valid_until": ex.valid_until,
                "issuer_dn": ex.issuer_dn,
                "issuer_cn": ex.issuer_cn,
                "issuer_organization": ex.issuer_organization,
                "fingerprint_hash": ex.fingerprint_hash,
                "notes": ex.notes,
                "updated_at": ex.updated_at,
            },
        ).returning(tbl.c.id, tbl.c.serial_number)
        ret = session.execute(ins).all()
        id_by_serial = {r.serial_number: r.id for r in ret}

        for m in meta:
            item = m["item"]
            sid = id_by_serial.get(m["serial"])
            if not sid:
                failed_count += 1
                continue
            success_count += 1
            if m["action"] == "created":
                created_count += 1
                created_assets.append(
                    {
                        "event": "asset.created",
                        "asset_type": "certificate",
                        "record_id": str(sid),
                        "subject_dn": item.get("subject_dn"),
                        "program_name": program_name,
                        "subject_cn": item.get("subject_cn"),
                        "issuer_cn": item.get("issuer_cn"),
                        "valid_from": item.get("valid_from"),
                        "valid_until": item.get("valid_until"),
                        "serial_number": m["serial"],
                    }
                )
            elif m["action"] == "updated":
                updated_count += 1
                updated_assets.append(
                    {
                        "event": "asset.updated",
                        "asset_type": "certificate",
                        "record_id": str(sid),
                        "subject_dn": item.get("subject_dn"),
                        "program_name": program_name,
                        "subject_cn": item.get("subject_cn"),
                        "issuer_cn": item.get("issuer_cn"),
                        "valid_from": item.get("valid_from"),
                        "valid_until": item.get("valid_until"),
                        "serial_number": m["serial"],
                    }
                )
            else:
                skipped_count += 1
                skipped_assets.append(
                    {
                        "record_id": str(sid),
                        "subject_dn": item.get("subject_dn"),
                        "program_name": program_name,
                        "reason": "duplicate",
                    }
                )

        session.commit()
    except Exception:
        session.rollback()
        logger.exception("bulk_sql certificates chunk failed")
        raise
    finally:
        session.close()

    logger.info(
        "bulk_sql certificates chunk program=%s items=%s created=%s updated=%s skipped=%s wall_ms=%.1f",
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


async def bulk_create_or_update_certificates_all(
    certificates: List[Dict[str, Any]],
    program_name: str,
) -> Tuple[int, int, int, int, int, List[Dict], List[Dict], List[Dict]]:
    import asyncio

    chunk_sz = sql_chunk_size()
    sc = fc = cc = uc = sk = 0
    ca: List[Dict] = []
    ua: List[Dict] = []
    sa: List[Dict] = []
    for i in range(0, len(certificates), chunk_sz):
        p = await asyncio.to_thread(
            upsert_certificates_chunk, program_name, certificates[i : i + chunk_sz]
        )
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
