"""Chunked bulk upsert for URLs (PostgreSQL; simplified vs full ORM path)."""

from __future__ import annotations

import ipaddress
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from db import BatchSessionLocal
from models.postgres import ApexDomain, Program, Subdomain, URL
from repository.bulk_sql.config import sql_chunk_size
from repository.bulk_sql.scope import domain_in_scope
from utils.asset_source import apply_lazy_source, normalize_asset_source
from utils.domain_utils import extract_apex_domain, normalize_hostname
from utils.url_utils import normalize_url_asset_payload

logger = logging.getLogger(__name__)


def _hostname(item: Dict[str, Any]) -> Optional[str]:
    h = item.get("hostname")
    if h:
        return normalize_hostname(str(h)) or None
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


def _hostname_is_ip(hostname: str) -> bool:
    try:
        ipaddress.ip_address(hostname)
        return True
    except ValueError:
        return False


def _bulk_ensure_subdomains_for_hosts(
    session,
    program: Program,
    program_name: str,
    hostnames: List[str],
    source_by_host: Dict[str, Optional[str]],
    now_naive: datetime,
) -> tuple[Dict[str, uuid.UUID], List[Dict[str, Any]]]:
    """Upsert apex + subdomain rows for URL hostnames; return id map and created events."""
    implicit_events: List[Dict[str, Any]] = []
    subdomain_id_by_host: Dict[str, uuid.UUID] = {}
    if not hostnames:
        return subdomain_id_by_host, implicit_events

    distinct_hosts = sorted(set(hostnames))
    apex_by_host: Dict[str, str] = {}
    for host in distinct_hosts:
        try:
            apex_by_host[host] = extract_apex_domain(host)
        except ValueError:
            continue

    distinct_apex = sorted(set(apex_by_host.values()))
    if not distinct_apex:
        return subdomain_id_by_host, implicit_events

    apex_source_by_name: Dict[str, Optional[str]] = {}
    for host, apex_name in apex_by_host.items():
        src = source_by_host.get(host)
        if src and apex_name not in apex_source_by_name:
            apex_source_by_name[apex_name] = src

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
                    "source": apex_source_by_name.get(nm),
                    "created_at": now_naive,
                    "updated_at": now_naive,
                }
                for nm in distinct_apex
            ]
        )
        .on_conflict_do_nothing(index_elements=[apex_tbl.c.name, apex_tbl.c.program_id])
        .returning(apex_tbl.c.id, apex_tbl.c.name)
    )
    inserted_apex = session.execute(apex_insert).all()
    for row in inserted_apex:
        implicit_events.append(
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
    apex_id_by_name = {r.name: r.id for r in apex_rows}

    existing_subs = session.execute(
        select(Subdomain.id, Subdomain.name).where(
            Subdomain.program_id == program.id,
            Subdomain.name.in_(distinct_hosts),
        )
    ).all()
    existing_sub_names = {r.name for r in existing_subs}
    for row in existing_subs:
        subdomain_id_by_host[row.name] = row.id

    new_sub_rows: List[Dict[str, Any]] = []
    new_sub_meta: List[tuple[str, str]] = []
    for host in distinct_hosts:
        if host in existing_sub_names:
            continue
        apex_name = apex_by_host.get(host)
        apex_id = apex_id_by_name.get(apex_name) if apex_name else None
        if not apex_id:
            continue
        new_sub_rows.append(
            {
                "id": uuid.uuid4(),
                "name": host,
                "program_id": program.id,
                "apex_domain_id": apex_id,
                "is_wildcard": False,
                "wildcard_types": [],
                "cname_record": None,
                "notes": None,
                "source": source_by_host.get(host),
                "created_at": now_naive,
                "updated_at": now_naive,
            }
        )
        new_sub_meta.append((host, apex_name or host))

    if new_sub_rows:
        sub_tbl = Subdomain.__table__
        ins = (
            insert(sub_tbl)
            .values(new_sub_rows)
            .on_conflict_do_nothing(index_elements=[sub_tbl.c.name, sub_tbl.c.program_id])
            .returning(sub_tbl.c.id, sub_tbl.c.name)
        )
        inserted_subs = session.execute(ins).all()
        apex_label_by_host = dict(new_sub_meta)
        for row in inserted_subs:
            subdomain_id_by_host[row.name] = row.id
            implicit_events.append(
                {
                    "event": "asset.created",
                    "asset_type": "subdomain",
                    "record_id": str(row.id),
                    "name": row.name,
                    "program_name": program_name,
                    "apex_domain": apex_label_by_host.get(row.name, row.name),
                    "ip": [],
                    "cname_record": None,
                    "is_wildcard": False,
                }
            )

    return subdomain_id_by_host, implicit_events


def upsert_urls_chunk(program_id: str, items: List[Dict[str, Any]]) -> Dict[str, Any]:
    session = BatchSessionLocal()
    success_count = failed_count = 0
    created_count = updated_count = skipped_count = 0
    created_assets: List[Dict] = []
    updated_assets: List[Dict] = []
    skipped_assets: List[Dict] = []
    implicit_created_events: List[Dict] = []
    t0 = time.perf_counter()

    try:
        try:
            pid = uuid.UUID(str(program_id))
        except ValueError as e:
            raise ValueError(f"Invalid program_id: {program_id!r}") from e
        program = session.execute(select(Program).where(Program.id == pid)).scalar_one_or_none()
        if not program:
            raise ValueError(f"Program id {program_id!r} not found")
        program_name_disp = program.name

        now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
        domain_regex = program.domain_regex or []
        oos_regex = program.out_of_scope_regex or []
        scope_domains = getattr(program, "scope_domains", None) or []
        out_of_scope_domains = getattr(program, "out_of_scope_domains", None) or []

        dedup: Dict[str, Dict[str, Any]] = {}
        order: List[str] = []
        for raw in items:
            item = dict(raw)
            if not item.get("program_name"):
                item["program_name"] = program_name_disp
            u_raw = item.get("url")
            if not u_raw:
                failed_count += 1
                skipped_assets.append(
                    {
                        "url": "unknown",
                        "program_name": program_name_disp,
                        "error": "missing_url",
                    }
                )
                continue
            u_norm = normalize_url_asset_payload(item)
            if not u_norm:
                failed_count += 1
                skipped_assets.append(
                    {
                        "url": str(u_raw),
                        "program_name": program_name_disp,
                        "error": "invalid_url",
                    }
                )
                continue
            if u_norm in dedup:
                failed_count += 1
                skipped_assets.append(
                    {
                        "url": u_norm,
                        "program_name": program_name_disp,
                        "error": "duplicate_url_in_batch",
                    }
                )
                continue
            order.append(u_norm)
            dedup[u_norm] = item

        pending_urls: List[tuple[str, Dict[str, Any], str]] = []
        hostnames_for_sub: List[str] = []
        source_by_host: Dict[str, Optional[str]] = {}
        for url_s in order:
            item = dedup[url_s]
            host = item.get("hostname") or _hostname(item)
            if not host or not domain_in_scope(
                host,
                list(domain_regex),
                list(oos_regex),
                list(scope_domains) if scope_domains else [],
                list(out_of_scope_domains) if out_of_scope_domains else [],
            ):
                failed_count += 1
                skipped_assets.append(
                    {
                        "url": url_s,
                        "program_name": program_name_disp,
                        "error": "out_of_scope" if host else "bad_hostname",
                    }
                )
                continue
            pending_urls.append((url_s, item, host))
            if not _hostname_is_ip(host):
                hostnames_for_sub.append(host)
                src = normalize_asset_source(item.get("source"))
                if src and host not in source_by_host:
                    source_by_host[host] = src

        subdomain_id_by_host, sub_implicit = _bulk_ensure_subdomains_for_hosts(
            session,
            program,
            program_name_disp,
            hostnames_for_sub,
            source_by_host,
            now_naive,
        )
        implicit_created_events.extend(sub_implicit)

        rows: List[Dict[str, Any]] = []
        meta: List[Dict[str, Any]] = []

        for url_s, item, host in pending_urls:
            existing = session.execute(
                select(URL).where(URL.url == url_s, URL.program_id == program.id)
            ).scalar_one_or_none()

            cert_id = _uuid_or_none(item.get("certificate_id"))
            sub_id = _uuid_or_none(item.get("subdomain_id")) or subdomain_id_by_host.get(host)

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
            incoming_source = normalize_asset_source(item.get("source"))
            meaningful = False
            if existing:
                row = {
                    "id": existing.id,
                    "url": url_s,
                    "hostname": item.get("hostname") or host,
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
                    "source": apply_lazy_source(existing.source, incoming_source),
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
                        "hostname": item.get("hostname") or host,
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
                        "source": incoming_source,
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
                implicit_created_events,
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
                "source": func.coalesce(tbl.c.source, ex.source),
                "updated_at": ex.updated_at,
            },
        ).returning(tbl.c.id, tbl.c.url)
        ret = session.execute(ins).all()
        if len(ret) != len(meta):
            logger.warning(
                "bulk_sql urls RETURNING row count mismatch program_id=%r: meta=%s ret=%s",
                program_id,
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
                        "program_name": program_name_disp,
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
                        "program_name": program_name_disp,
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
                        "program_name": program_name_disp,
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
                        "program_name": program_name_disp,
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
        "bulk_sql urls chunk program_id=%s items=%s created=%s updated=%s skipped=%s failed=%s wall_ms=%.1f",
        program_id,
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
        implicit_created_events,
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
    implicit_created_events: List[Dict],
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
        "implicit_created_events": implicit_created_events,
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
    program_id: str,
) -> Tuple[int, int, int, int, int, List[Dict], List[Dict], List[Dict], List[Dict]]:
    import asyncio

    chunk_sz = sql_chunk_size()
    sc = fc = cc = uc = sk = 0
    ca: List[Dict] = []
    ua: List[Dict] = []
    sa: List[Dict] = []
    implicit: List[Dict] = []
    for i in range(0, len(urls), chunk_sz):
        p = await asyncio.to_thread(upsert_urls_chunk, program_id, urls[i : i + chunk_sz])
        sc += p["success_count"]
        fc += p["failed_count"]
        cc += p["created_count"]
        uc += p["updated_count"]
        sk += p["skipped_count"]
        ca.extend(p["created_assets"])
        ua.extend(p["updated_assets"])
        sa.extend(p["skipped_assets"])
        implicit.extend(p.get("implicit_created_events", []))
        await asyncio.sleep(0)
    return sc, fc, cc, uc, sk, ca, ua, sa, implicit
