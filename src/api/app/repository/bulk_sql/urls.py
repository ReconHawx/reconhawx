"""Chunked bulk upsert for URLs (PostgreSQL; simplified vs full ORM path)."""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from db import BatchSessionLocal
from models.postgres import Program, URL
from repository.bulk_sql.config import sql_chunk_size
from repository.bulk_sql.scope import domain_in_scope

logger = logging.getLogger(__name__)


def _hostname(item: Dict[str, Any]) -> Optional[str]:
    h = item.get("hostname")
    if h:
        return str(h).strip()
    u = item.get("url")
    if not u:
        return None
    try:
        return urlparse(u).hostname
    except Exception:
        return None


def _uuid_or_none(v: Any) -> Optional[uuid.UUID]:
    if v is None or v == "":
        return None
    try:
        return uuid.UUID(str(v))
    except (ValueError, TypeError):
        return None


def upsert_urls_chunk(program_name: str, items: List[Dict[str, Any]]) -> Dict[str, Any]:
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
        domain_regex = program.domain_regex or []
        oos_regex = program.out_of_scope_regex or []

        dedup: Dict[str, Dict[str, Any]] = {}
        order: List[str] = []
        for raw in items:
            item = dict(raw)
            if not item.get("program_name"):
                item["program_name"] = program_name
            u = item.get("url")
            if not u:
                failed_count += 1
                skipped_assets.append(
                    {
                        "url": "unknown",
                        "program_name": program_name,
                        "error": "missing_url",
                    }
                )
                continue
            if u in dedup:
                failed_count += 1
                skipped_assets.append(
                    {
                        "url": u,
                        "program_name": program_name,
                        "error": "duplicate_url_in_batch",
                    }
                )
                continue
            order.append(u)
            dedup[u] = item

        rows: List[Dict[str, Any]] = []
        meta: List[Dict[str, Any]] = []

        for url_s in order:
            item = dedup[url_s]
            host = _hostname(item)
            if not host or not domain_in_scope(host, list(domain_regex), list(oos_regex)):
                # Match legacy batch_repository: no record_id for out-of-scope URL counts as failed.
                failed_count += 1
                skipped_assets.append(
                    {
                        "url": url_s,
                        "program_name": program_name,
                        "error": "out_of_scope" if host else "bad_hostname",
                    }
                )
                continue

            existing = session.execute(
                select(URL).where(URL.url == url_s, URL.program_id == program.id)
            ).scalar_one_or_none()

            cert_id = _uuid_or_none(item.get("certificate_id"))
            sub_id = _uuid_or_none(item.get("subdomain_id"))

            simple_fields = [
                "http_status_code",
                "content_type",
                "content_length",
                "line_count",
                "word_count",
                "title",
                "final_url",
                "response_body_hash",
                "body_preview",
            ]
            meaningful = False
            if existing:
                row = {
                    "id": existing.id,
                    "url": url_s,
                    "hostname": host,
                    "port": item.get("port", existing.port),
                    "path": item.get("path", existing.path),
                    "scheme": item.get("scheme", existing.scheme),
                    "http_status_code": existing.http_status_code,
                    "http_method": item.get("http_method", existing.http_method or "GET"),
                    "response_time_ms": item.get("response_time_ms", existing.response_time_ms),
                    "content_type": existing.content_type,
                    "content_length": existing.content_length,
                    "line_count": existing.line_count,
                    "word_count": existing.word_count,
                    "title": existing.title,
                    "final_url": existing.final_url,
                    "response_body_hash": existing.response_body_hash,
                    "body_preview": existing.body_preview,
                    "favicon_hash": item.get("favicon_hash", existing.favicon_hash),
                    "favicon_url": item.get("favicon_url", existing.favicon_url),
                    "redirect_chain": item.get("redirect_chain", existing.redirect_chain),
                    "chain_status_codes": item.get("chain_status_codes", existing.chain_status_codes),
                    "certificate_id": existing.certificate_id,
                    "subdomain_id": existing.subdomain_id,
                    "program_id": program.id,
                    "notes": existing.notes,
                    "created_at": existing.created_at,
                    "updated_at": existing.updated_at,
                }
                for f in simple_fields:
                    if f in item and item[f] is not None and item[f] != getattr(existing, f):
                        row[f] = item[f]
                        meaningful = True
                if item.get("notes") is not None and item.get("notes") != existing.notes:
                    row["notes"] = item.get("notes")
                    meaningful = True
                if cert_id is not None and cert_id != existing.certificate_id:
                    row["certificate_id"] = cert_id
                    meaningful = True
                if sub_id is not None and sub_id != existing.subdomain_id:
                    row["subdomain_id"] = sub_id
                    meaningful = True
                row["updated_at"] = now_naive if meaningful else existing.updated_at
                rows.append(row)
                meta.append({"item": item, "action": "updated" if meaningful else "skipped"})
            else:
                rows.append(
                    {
                        "id": uuid.uuid4(),
                        "url": url_s,
                        "hostname": host,
                        "port": item.get("port"),
                        "path": item.get("path"),
                        "scheme": item.get("scheme"),
                        "http_status_code": item.get("http_status_code"),
                        "http_method": item.get("http_method", "GET"),
                        "response_time_ms": item.get("response_time_ms"),
                        "content_type": item.get("content_type"),
                        "content_length": item.get("content_length"),
                        "line_count": item.get("line_count"),
                        "word_count": item.get("word_count"),
                        "title": item.get("title"),
                        "final_url": item.get("final_url"),
                        "response_body_hash": item.get("response_body_hash"),
                        "body_preview": item.get("body_preview"),
                        "favicon_hash": item.get("favicon_hash"),
                        "favicon_url": item.get("favicon_url"),
                        "redirect_chain": item.get("redirect_chain"),
                        "chain_status_codes": item.get("chain_status_codes", []),
                        "certificate_id": cert_id,
                        "subdomain_id": sub_id,
                        "program_id": program.id,
                        "notes": item.get("notes"),
                        "created_at": now_naive,
                        "updated_at": now_naive,
                    }
                )
                meta.append({"item": item, "action": "created"})

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

        tbl = URL.__table__
        ins = insert(tbl).values(rows)
        ex = ins.excluded
        ins = ins.on_conflict_do_update(
            index_elements=[tbl.c.url, tbl.c.program_id],
            set_={
                "hostname": ex.hostname,
                "port": ex.port,
                "path": ex.path,
                "scheme": ex.scheme,
                "http_status_code": ex.http_status_code,
                "http_method": ex.http_method,
                "response_time_ms": ex.response_time_ms,
                "content_type": ex.content_type,
                "content_length": ex.content_length,
                "line_count": ex.line_count,
                "word_count": ex.word_count,
                "title": ex.title,
                "final_url": ex.final_url,
                "response_body_hash": ex.response_body_hash,
                "body_preview": ex.body_preview,
                "favicon_hash": ex.favicon_hash,
                "favicon_url": ex.favicon_url,
                "redirect_chain": ex.redirect_chain,
                "chain_status_codes": ex.chain_status_codes,
                "certificate_id": ex.certificate_id,
                "subdomain_id": ex.subdomain_id,
                "notes": ex.notes,
                "updated_at": ex.updated_at,
            },
        ).returning(tbl.c.id, tbl.c.url)
        ret = session.execute(ins).all()
        if len(ret) != len(meta):
            logger.warning(
                "bulk_sql urls RETURNING row count mismatch program=%r: meta=%s ret=%s",
                program_name,
                len(meta),
                len(ret),
            )
        # Map RETURNING rows by column name (avoid brittle row[0]/row[1] ordering).
        id_by_url: Dict[str, Any] = {}
        for row in ret:
            rm = row._mapping
            id_by_url[str(rm["url"])] = rm["id"]

        for m in meta:
            item = m["item"]
            u = item["url"]
            uid = id_by_url.get(str(u))
            if not uid:
                failed_count += 1
                skipped_assets.append(
                    {
                        "url": u,
                        "program_name": program_name,
                        "error": "returning_missing_id",
                    }
                )
                continue
            success_count += 1
            if m["action"] == "created":
                created_count += 1
                created_assets.append(
                    {
                        "event": "asset.created",
                        "asset_type": "url",
                        "record_id": str(uid),
                        "url": u,
                        "path": item.get("path"),
                        "program_name": program_name,
                        "http_status_code": item.get("http_status_code"),
                        "content_type": item.get("content_type"),
                        "title": item.get("title"),
                        "technologies": item.get("technologies", []),
                    }
                )
            elif m["action"] == "updated":
                updated_count += 1
                updated_assets.append(
                    {
                        "event": "asset.updated",
                        "asset_type": "url",
                        "record_id": str(uid),
                        "url": u,
                        "path": item.get("path"),
                        "program_name": program_name,
                        "http_status_code": item.get("http_status_code"),
                        "content_type": item.get("content_type"),
                        "title": item.get("title"),
                        "technologies": item.get("technologies", []),
                    }
                )
            else:
                skipped_count += 1
                skipped_assets.append(
                    {
                        "record_id": str(uid),
                        "url": u,
                        "program_name": program_name,
                        "reason": "duplicate",
                    }
                )

        session.commit()
    except Exception:
        session.rollback()
        logger.exception("bulk_sql urls chunk failed")
        raise
    finally:
        session.close()

    logger.info(
        "bulk_sql urls chunk program=%s items=%s created=%s updated=%s skipped=%s failed=%s wall_ms=%.1f",
        program_name,
        len(items),
        created_count,
        updated_count,
        skipped_count,
        failed_count,
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


def urls_require_full_orm(urls: List[Dict[str, Any]]) -> bool:
    """Technologies / extracted links need the legacy ORM path."""
    for u in urls:
        if u.get("technologies") or u.get("extracted_links"):
            return True
    return False


async def bulk_create_or_update_urls_all(
    urls: List[Dict[str, Any]],
    program_name: str,
) -> Tuple[int, int, int, int, int, List[Dict], List[Dict], List[Dict]]:
    import asyncio

    chunk_sz = sql_chunk_size()
    sc = fc = cc = uc = sk = 0
    ca: List[Dict] = []
    ua: List[Dict] = []
    sa: List[Dict] = []
    for i in range(0, len(urls), chunk_sz):
        p = await asyncio.to_thread(upsert_urls_chunk, program_name, urls[i : i + chunk_sz])
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
