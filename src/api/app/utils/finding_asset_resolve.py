"""Resolve finding string fields to in-scope asset UUIDs at ingest time."""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from typing import Any, Optional, Set
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from models.postgres import IP, Service, Subdomain, URL
from repository.task_history_repo import url_match_variants
from utils.domain_utils import normalize_hostname
from utils.url_utils import get_root_url, normalize_url_for_storage

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResolvedFindingAssets:
    subdomain_id: Optional[UUID] = None
    url_id: Optional[UUID] = None
    ip_id: Optional[UUID] = None
    service_id: Optional[UUID] = None


def _looks_like_url(s: str) -> bool:
    sl = s.lower().strip()
    return sl.startswith("http://") or sl.startswith("https://")


def url_lookup_variants(raw: str) -> Set[str]:
    """URL forms for matching canonical ``urls.url`` rows (``scheme://hostname:port/path``)."""
    s = str(raw).strip()
    if not s:
        return set()
    variants: Set[str] = set()
    variants.update(url_match_variants(s))
    if _looks_like_url(s):
        stored = normalize_url_for_storage(s)
        if stored:
            variants.update(url_match_variants(stored))
        root = get_root_url(s)
        if root:
            root_canonical = normalize_url_for_storage(root) or root
            variants.update(url_match_variants(root_canonical))
    return {v for v in variants if v}


def _lookup_url_id(db: Session, program_id: UUID, variants: Set[str]) -> Optional[UUID]:
    if not variants:
        return None
    variant_list = list(variants)
    row = (
        db.query(URL.id)
        .filter(URL.program_id == program_id, URL.url.in_(variant_list))
        .first()
    )
    if row:
        return row[0]
    # urls.url is globally unique; allow match when program_id on the row differs
    row = db.query(URL.id).filter(URL.url.in_(variant_list)).first()
    if row:
        return row[0]
    return None


def _coerce_port(port: Any) -> Optional[int]:
    if port is None or port == "":
        return None
    try:
        return int(port)
    except (TypeError, ValueError):
        return None


def resolve_finding_asset_ids(
    db: Session,
    program_id: UUID,
    *,
    hostname: Optional[str] = None,
    url: Optional[str] = None,
    ip: Optional[str] = None,
    port: Any = None,
    resolve_subdomain: bool = True,
    resolve_url: bool = True,
    resolve_ip: bool = True,
    resolve_service: bool = True,
) -> ResolvedFindingAssets:
    """Look up asset rows for a program from finding hostname/url/ip/port strings."""
    subdomain_id: Optional[UUID] = None
    url_id: Optional[UUID] = None
    ip_id: Optional[UUID] = None
    service_id: Optional[UUID] = None

    if resolve_subdomain and hostname:
        host = normalize_hostname(str(hostname))
        if host:
            sub = (
                db.query(Subdomain.id)
                .filter(
                    Subdomain.program_id == program_id,
                    Subdomain.name == host,
                )
                .first()
            )
            if sub:
                subdomain_id = sub[0]

    if resolve_url and url:
        url_id = _lookup_url_id(db, program_id, url_lookup_variants(str(url)))

    if resolve_ip and ip:
        ip_str = str(ip).strip()
        if ip_str:
            row = (
                db.query(IP.id)
                .filter(
                    IP.program_id == program_id,
                    func.host(IP.ip_address) == ip_str,
                )
                .first()
            )
            if row:
                ip_id = row[0]

    port_int = _coerce_port(port)
    if resolve_service and ip_id is not None and port_int is not None:
        svc = (
            db.query(Service.id)
            .filter(
                Service.program_id == program_id,
                Service.ip_id == ip_id,
                Service.port == port_int,
            )
            .first()
        )
        if svc:
            service_id = svc[0]

    return ResolvedFindingAssets(
        subdomain_id=subdomain_id,
        url_id=url_id,
        ip_id=ip_id,
        service_id=service_id,
    )


async def ensure_finding_url_asset(
    program_name: str,
    *,
    url: str,
    hostname: Optional[str] = None,
    port: Any = None,
    scheme: Optional[str] = None,
) -> Optional[UUID]:
    """Create or upsert a canonical URL asset when ingest lookup finds no row."""
    from repository.url_assets_repo import UrlAssetsRepository

    canonical = normalize_url_for_storage(str(url).strip()) or str(url).strip()
    if not canonical:
        return None

    url_data: dict[str, Any] = {
        "url": canonical,
        "program_name": program_name,
        "source": "finding_ingest",
    }
    if hostname:
        url_data["hostname"] = normalize_hostname(str(hostname))
    port_int = _coerce_port(port)
    if port_int is not None:
        url_data["port"] = port_int
    if scheme:
        url_data["scheme"] = str(scheme).lower()

    try:
        url_id_str, action, _, _ = await UrlAssetsRepository.create_or_update_url(url_data)
    except Exception:
        logger.exception("Failed to ensure URL asset for finding url=%s", canonical)
        return None

    if not url_id_str:
        return None
    try:
        return UUID(str(url_id_str))
    except (TypeError, ValueError):
        return None


async def resolve_finding_asset_ids_with_url_ensure(
    db: Session,
    program_id: UUID,
    program_name: str,
    *,
    hostname: Optional[str] = None,
    url: Optional[str] = None,
    ip: Optional[str] = None,
    port: Any = None,
    scheme: Optional[str] = None,
    resolve_subdomain: bool = True,
    resolve_url: bool = True,
    resolve_ip: bool = True,
    resolve_service: bool = True,
) -> ResolvedFindingAssets:
    """Resolve asset FKs; create URL asset when missing but ``url`` is present."""
    resolved = resolve_finding_asset_ids(
        db,
        program_id,
        hostname=hostname,
        url=url,
        ip=ip,
        port=port,
        resolve_subdomain=resolve_subdomain,
        resolve_url=resolve_url,
        resolve_ip=resolve_ip,
        resolve_service=resolve_service,
    )
    if not resolve_url or not url or resolved.url_id is not None:
        return resolved

    ensured = await ensure_finding_url_asset(
        program_name,
        url=str(url),
        hostname=hostname,
        port=port,
        scheme=scheme,
    )
    if ensured is None:
        return resolved

    updated = replace(resolved, url_id=ensured)
    if resolve_subdomain and updated.subdomain_id is None:
        url_sub = db.query(URL.subdomain_id).filter(URL.id == ensured).first()
        if url_sub and url_sub[0]:
            updated = replace(updated, subdomain_id=url_sub[0])
    return updated
