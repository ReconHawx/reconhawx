"""
Unified persistence for scanner findings (Nuclei, WPScan, Broken Links).

Type-specific fields live in ``Finding.details`` JSONB; see migration / plan.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, asc, cast, desc, func, or_, Text

from db import get_db_session, SessionLocal
from fastapi.concurrency import run_in_threadpool
from models.base import utcnow
from models.postgres import IP, Finding, Program, URL, Subdomain, ApexDomain
from services.event_publisher import publisher
from utils.domain_utils import normalize_hostname
from utils.finding_fingerprint import (
    fingerprint_broken_link,
    fingerprint_nuclei,
    fingerprint_wpscan,
)
from utils.finding_asset_resolve import resolve_finding_asset_ids_with_url_ensure
from utils.program_resolve import resolve_program_from_payload
from utils.query_filters import ProgramAccessMixin, QueryFilterUtils
from utils.url_utils import lower_url_host, normalize_url_for_storage

logger = logging.getLogger(__name__)

SOURCE_NUCLEI = "nuclei"
SOURCE_WPSCAN = "wpscan"
SOURCE_BROKEN_LINK = "broken_link"


def _parse_uuid_filter(value: Optional[str]) -> Optional[uuid.UUID]:
    if value is None or not str(value).strip():
        return None
    try:
        return uuid.UUID(str(value).strip())
    except ValueError:
        return None


def _apply_finding_asset_fk_filters(
    q,
    *,
    url_id: Optional[str] = None,
    subdomain_id: Optional[str] = None,
    ip_id: Optional[str] = None,
    service_id: Optional[str] = None,
    certificate_id: Optional[str] = None,
    apex_domain: Optional[str] = None,
):
    """Apply optional asset FK / relation filters to a findings query."""
    url_uuid = _parse_uuid_filter(url_id)
    if url_uuid is not None:
        q = q.filter(Finding.url_id == url_uuid)

    subdomain_uuid = _parse_uuid_filter(subdomain_id)
    if subdomain_uuid is not None:
        q = q.filter(Finding.subdomain_id == subdomain_uuid)

    ip_uuid = _parse_uuid_filter(ip_id)
    if ip_uuid is not None:
        q = q.filter(Finding.ip_id == ip_uuid)

    service_uuid = _parse_uuid_filter(service_id)
    if service_uuid is not None:
        q = q.filter(Finding.service_id == service_uuid)

    cert_uuid = _parse_uuid_filter(certificate_id)
    if cert_uuid is not None:
        q = q.join(URL, Finding.url_id == URL.id).filter(URL.certificate_id == cert_uuid)

    if apex_domain and str(apex_domain).strip():
        q = (
            q.join(Subdomain, Finding.subdomain_id == Subdomain.id)
            .join(ApexDomain, Subdomain.apex_domain_id == ApexDomain.id)
            .filter(ApexDomain.name == str(apex_domain).strip())
        )

    return q


def _normalize_finding_url(url: Optional[str]) -> Optional[str]:
    """Canonical ``scheme://hostname:port/path`` for finding URL fields."""
    if url is None or not str(url).strip():
        return url
    s = str(url).strip()
    canonical = normalize_url_for_storage(s)
    return canonical if canonical else s


def _parse_observed_at(matched_at: Any) -> Optional[datetime]:
    if matched_at is None:
        return None
    if isinstance(matched_at, datetime):
        return matched_at
    s = str(matched_at).strip()
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


def _jsonb_list(val: Any) -> List[Any]:
    """Normalize a ``details`` JSON array field to a Python list for API output."""
    if val is None:
        return []
    if isinstance(val, list):
        return val
    return []


def _nuclei_info_from_payload(finding_data: Dict[str, Any]) -> Dict[str, Any]:
    inf = finding_data.get("info")
    if isinstance(inf, dict):
        return inf
    inf2 = finding_data.get("info_data")
    if isinstance(inf2, dict):
        return inf2
    return {}


def _nuclei_payload_to_details(finding_data: Dict[str, Any]) -> Dict[str, Any]:
    raw_tags = finding_data.get("tags")
    tags_list = raw_tags if isinstance(raw_tags, list) else []
    return {
        "template_id": finding_data.get("template_id"),
        "template_url": finding_data.get("template_url"),
        "template_path": finding_data.get("template_path"),
        "type": finding_data.get("type"),
        "matched_at": finding_data.get("matched_at"),
        "matcher_name": finding_data.get("matcher_name"),
        "matched_line": finding_data.get("matched_line"),
        "extracted_results": finding_data.get("extracted_results") or [],
        "info": _nuclei_info_from_payload(finding_data),
        "protocol": finding_data.get("protocol"),
        "tags": tags_list,
    }


def _finding_asset_ids_dict(f: Finding) -> Dict[str, Optional[str]]:
    return {
        "domain_id": str(f.subdomain_id) if f.subdomain_id else None,
        "url_id": str(f.url_id) if f.url_id else None,
        "ip_id": str(f.ip_id) if f.ip_id else None,
        "service_id": str(f.service_id) if f.service_id else None,
    }


def _apply_resolved_assets_to_finding(
    finding: Finding,
    resolved,
    *,
    apply_subdomain: bool = True,
    apply_url: bool = True,
    apply_ip: bool = True,
    apply_service: bool = True,
) -> bool:
    """Set resolved asset FKs on a Finding row; return True if any column changed."""
    updated = False
    if apply_subdomain and finding.subdomain_id != resolved.subdomain_id:
        finding.subdomain_id = resolved.subdomain_id
        updated = True
    if apply_url and finding.url_id != resolved.url_id:
        finding.url_id = resolved.url_id
        updated = True
    if apply_ip and finding.ip_id != resolved.ip_id:
        finding.ip_id = resolved.ip_id
        updated = True
    if apply_service and finding.service_id != resolved.service_id:
        finding.service_id = resolved.service_id
        updated = True
    return updated


def _nuclei_dict_from_finding(f: Finding) -> Dict[str, Any]:
    d: Dict[str, Any] = dict(f.details or {})
    info = d.get("info")
    if not isinstance(info, dict):
        info = {}
    return {
        "id": str(f.id),
        "url": f.url,
        "template_id": d.get("template_id"),
        "template_url": d.get("template_url"),
        "template_path": d.get("template_path"),
        "name": f.title,
        "severity": f.severity,
        "type": d.get("type"),
        "tags": _jsonb_list(d.get("tags")),
        "description": f.description,
        "matched_at": d.get("matched_at"),
        "matcher_name": d.get("matcher_name"),
        "ip": f.ip.ip_address if f.ip else None,
        "hostname": f.hostname,
        "port": f.port,
        "scheme": f.scheme,
        "protocol": d.get("protocol"),
        "matched_line": d.get("matched_line"),
        "extracted_results": d.get("extracted_results") or [],
        "info": info,
        "program_name": f.program.name if f.program else None,
        "notes": f.notes,
        "status": d.get("status"),
        "assigned_to": None,
        "created_at": f.created_at.isoformat() if f.created_at else None,
        "updated_at": f.updated_at.isoformat() if f.updated_at else None,
        **_finding_asset_ids_dict(f),
    }


def _wpscan_payload_to_details(finding_data: Dict[str, Any]) -> Dict[str, Any]:
    refs = finding_data.get("references")
    cves = finding_data.get("cve_ids")
    return {
        "item_name": finding_data.get("item_name"),
        "item_type": finding_data.get("item_type"),
        "vulnerability_type": finding_data.get("vulnerability_type"),
        "fixed_in": finding_data.get("fixed_in"),
        "enumeration_data": finding_data.get("enumeration_data"),
        "status": finding_data.get("status"),
        "references": list(refs) if isinstance(refs, list) else [],
        "cve_ids": list(cves) if isinstance(cves, list) else [],
    }


def _wpscan_dict_from_finding(f: Finding) -> Dict[str, Any]:
    d: Dict[str, Any] = dict(f.details or {})
    return {
        "id": str(f.id),
        "url": f.url,
        "item_name": d.get("item_name"),
        "item_type": d.get("item_type"),
        "vulnerability_type": d.get("vulnerability_type"),
        "severity": f.severity,
        "title": f.title,
        "description": f.description,
        "fixed_in": d.get("fixed_in"),
        "references": _jsonb_list(d.get("references")),
        "cve_ids": _jsonb_list(d.get("cve_ids")),
        "enumeration_data": d.get("enumeration_data"),
        "hostname": f.hostname,
        "port": f.port,
        "scheme": f.scheme,
        "ip": str(f.ip.ip_address) if f.ip and f.ip.ip_address else None,
        "program_name": f.program.name if f.program else None,
        "notes": f.notes,
        "status": d.get("status"),
        "assigned_to": None,
        "created_at": f.created_at.isoformat() if f.created_at else None,
        "updated_at": f.updated_at.isoformat() if f.updated_at else None,
        **_finding_asset_ids_dict(f),
    }


def _broken_payload_to_details(finding_data: Dict[str, Any]) -> Dict[str, Any]:
    # ``details`` is a JSONB column, so any datetime must be serialized to a
    # string here — Pydantic's ``SerializedDatetime`` only kicks in for
    # ``model_dump(mode="json")``, and callers (e.g. the route) use the default
    # python-mode dump, which leaves ``checked_at`` as a raw ``datetime``.
    checked_at = finding_data.get("checked_at")
    if isinstance(checked_at, datetime):
        checked_at = checked_at.isoformat()
    return {
        "link_type": finding_data.get("link_type", "social_media"),
        "media_type": finding_data.get("media_type"),
        "domain": finding_data.get("domain"),
        "reason": finding_data.get("reason"),
        "error_code": finding_data.get("error_code"),
        "response_data": finding_data.get("response_data"),
        "checked_at": checked_at,
        "status": finding_data.get("status"),
    }


def _broken_dict_from_finding(f: Finding) -> Dict[str, Any]:
    d: Dict[str, Any] = dict(f.details or {})
    checked = d.get("checked_at")
    if isinstance(f.observed_at, datetime):
        checked_iso = f.observed_at.isoformat()
    elif checked is not None and hasattr(checked, "isoformat"):
        checked_iso = checked.isoformat()
    else:
        checked_iso = checked
    return {
        "id": str(f.id),
        "program_id": str(f.program_id),
        "program_name": f.program.name if f.program else None,
        "link_type": d.get("link_type"),
        "media_type": d.get("media_type"),
        "domain": d.get("domain"),
        "reason": d.get("reason"),
        "status": d.get("status"),
        "url": f.url,
        "error_code": d.get("error_code"),
        "response_data": d.get("response_data"),
        "checked_at": checked_iso,
        "notes": f.notes,
        "created_at": f.created_at.isoformat() if f.created_at else None,
        "updated_at": f.updated_at.isoformat() if f.updated_at else None,
    }


class FindingsRepository(ProgramAccessMixin):
    """CRUD/search for unified ``findings`` rows."""

    # ----- Nuclei -----
    @staticmethod
    async def create_or_update_nuclei_finding(finding_data: Dict[str, Any]) -> tuple[str, str]:
        async with get_db_session() as db:
            try:
                program = resolve_program_from_payload(db, finding_data)

                if finding_data.get("url"):
                    finding_data["url"] = _normalize_finding_url(finding_data.get("url"))
                if finding_data.get("hostname"):
                    finding_data["hostname"] = normalize_hostname(str(finding_data["hostname"]))
                if finding_data.get("template_url") and isinstance(finding_data["template_url"], str):
                    tu = finding_data["template_url"]
                    if tu.startswith(("http://", "https://")):
                        finding_data["template_url"] = lower_url_host(tu) or tu
                if finding_data.get("scheme") and isinstance(finding_data["scheme"], str):
                    finding_data["scheme"] = finding_data["scheme"].lower()

                fp = fingerprint_nuclei(
                    url=finding_data.get("url"),
                    template_id=finding_data.get("template_id"),
                    matcher_name=finding_data.get("matcher_name"),
                    program_id=program.id,
                    matched_at=finding_data.get("matched_at"),
                )
                existing = (
                    db.query(Finding)
                    .filter(
                        and_(
                            Finding.program_id == program.id,
                            Finding.source == SOURCE_NUCLEI,
                            Finding.fingerprint == fp,
                        )
                    )
                    .first()
                )
                details = _nuclei_payload_to_details(finding_data)
                observed = _parse_observed_at(finding_data.get("matched_at")) or utcnow()

                ip_for_resolve = finding_data.get("ip")
                if ip_for_resolve is None and existing and existing.ip_id:
                    existing_ip = existing.ip or db.query(IP).filter(IP.id == existing.ip_id).first()
                    if existing_ip and existing_ip.ip_address is not None:
                        ip_for_resolve = str(existing_ip.ip_address)

                finding_url = (
                    finding_data.get("url")
                    if "url" in finding_data
                    else (existing.url if existing else None)
                )
                finding_scheme = (
                    finding_data.get("scheme")
                    if "scheme" in finding_data
                    else (existing.scheme if existing else None)
                )
                resolved = await resolve_finding_asset_ids_with_url_ensure(
                    db,
                    program.id,
                    finding_data.get("program_name") or program.name,
                    hostname=finding_data.get("hostname")
                    if "hostname" in finding_data
                    else (existing.hostname if existing else None),
                    url=finding_url,
                    ip=ip_for_resolve,
                    port=finding_data.get("port")
                    if "port" in finding_data
                    else (existing.port if existing else None),
                    scheme=finding_scheme,
                )

                if existing:
                    updated = False
                    if (
                        "severity" in finding_data
                        and finding_data.get("severity") != existing.severity
                    ):
                        existing.severity = finding_data.get("severity")
                        updated = True
                    if (
                        "description" in finding_data
                        and finding_data.get("description") != existing.description
                    ):
                        existing.description = finding_data.get("description")
                        updated = True
                    if (
                        "name" in finding_data
                        and finding_data.get("name") != existing.title
                    ):
                        existing.title = finding_data.get("name")
                        updated = True
                    new_er = finding_data.get("extracted_results")
                    if new_er is not None:
                        cur = (existing.details or {}).get("extracted_results")
                        if new_er != cur:
                            merged = dict(existing.details or {})
                            merged["extracted_results"] = new_er
                            existing.details = merged
                            updated = True
                    if "info" in finding_data or "info_data" in finding_data:
                        new_info = _nuclei_info_from_payload(finding_data)
                        merged = dict(existing.details or {})
                        if merged.get("info") != new_info:
                            merged["info"] = new_info
                            existing.details = merged
                            updated = True
                    if (
                        "matched_line" in finding_data
                        and finding_data.get("matched_line")
                        != (existing.details or {}).get("matched_line")
                    ):
                        merged = dict(existing.details or {})
                        merged["matched_line"] = finding_data.get("matched_line")
                        existing.details = merged
                        updated = True
                    if "notes" in finding_data and finding_data.get("notes") != existing.notes:
                        existing.notes = finding_data.get("notes")
                        updated = True
                    if _apply_resolved_assets_to_finding(existing, resolved):
                        updated = True
                    for k, v in details.items():
                        skip_keys = ("extracted_results", "info", "matched_line")
                        if k in skip_keys:
                            continue
                        if v is None and k != "tags":
                            continue
                        if (existing.details or {}).get(k) != v:
                            merged = dict(existing.details or {})
                            merged[k] = v
                            existing.details = merged
                            updated = True
                    if updated:
                        existing.updated_at = utcnow()
                    db.commit()
                    return str(existing.id), "updated" if updated else "skipped"

                row = Finding(
                    id=uuid.uuid4(),
                    program_id=program.id,
                    source=SOURCE_NUCLEI,
                    fingerprint=fp,
                    title=finding_data.get("name"),
                    description=finding_data.get("description"),
                    severity=finding_data.get("severity"),
                    url=finding_data.get("url"),
                    hostname=finding_data.get("hostname"),
                    port=finding_data.get("port"),
                    scheme=finding_data.get("scheme"),
                    subdomain_id=resolved.subdomain_id,
                    url_id=resolved.url_id,
                    ip_id=resolved.ip_id,
                    service_id=resolved.service_id,
                    observed_at=observed,
                    notes=finding_data.get("notes"),
                    details=details,
                )
                db.add(row)
                db.commit()
                db.refresh(row)
                try:
                    await publisher.publish(
                        "events.findings.created.nuclei",
                        {
                            "event": "finding.created",
                            "type": "nuclei",
                            "program_name": finding_data.get("program_name"),
                            "record_id": str(row.id),
                            "severity": finding_data.get("severity"),
                            "template_id": finding_data.get("template_id"),
                            "url": finding_data.get("url"),
                        },
                    )
                except Exception:
                    pass
                return str(row.id), "created"
            except Exception as e:
                db.rollback()
                logger.error(f"Error creating/updating nuclei finding: {str(e)}")
                raise

    @staticmethod
    def _detail_text(col, key: str):
        """JSONB text extraction for filter/sort (PostgreSQL ``->>``)."""
        return col[key].astext

    @staticmethod
    def _nuclei_source_filter():
        return Finding.source == SOURCE_NUCLEI

    @staticmethod
    def _wpscan_source_filter():
        return Finding.source == SOURCE_WPSCAN

    @staticmethod
    def _broken_source_filter():
        return Finding.source == SOURCE_BROKEN_LINK

    @staticmethod
    def _nuclei_build_conditions(filters: Dict[str, Any]) -> tuple[List[Any], bool]:
        """Build SQLAlchemy conditions for Mongo-style nuclei filters. Returns (conditions, needs_ip_join)."""
        conditions: List[Any] = []
        needs_ip_join = False
        dt = FindingsRepository._detail_text
        if not filters:
            return conditions, needs_ip_join

        for key, value in filters.items():
            if key == "$and":
                groups = []
                for sub in value:
                    sub_conds, sub_ip = FindingsRepository._nuclei_build_conditions(sub)
                    needs_ip_join = needs_ip_join or sub_ip
                    if sub_conds:
                        groups.append(and_(*sub_conds))
                if groups:
                    conditions.append(and_(*groups))
            elif key == "$or":
                groups = []
                for sub in value:
                    sub_conds, sub_ip = FindingsRepository._nuclei_build_conditions(sub)
                    needs_ip_join = needs_ip_join or sub_ip
                    if sub_conds:
                        groups.append(and_(*sub_conds))
                if groups:
                    conditions.append(or_(*groups))
            elif key == "severity":
                conditions.append(Finding.severity == value)
            elif key == "name":
                if isinstance(value, dict) and "$regex" in value:
                    pattern = value.get("$regex", "")
                    options = value.get("$options", "")
                    if "i" in options:
                        conditions.append(Finding.title.ilike(f"%{pattern}%"))
                    else:
                        conditions.append(Finding.title.like(f"%{pattern}%"))
                else:
                    conditions.append(Finding.title == value)
            elif key == "template_id":
                if isinstance(value, dict) and "$regex" in value:
                    pattern = value.get("$regex", "")
                    options = value.get("$options", "")
                    if "i" in options:
                        conditions.append(dt(Finding.details, "template_id").ilike(f"%{pattern}%"))
                    else:
                        conditions.append(dt(Finding.details, "template_id").like(f"%{pattern}%"))
                else:
                    conditions.append(dt(Finding.details, "template_id") == value)
            elif key == "hostname":
                conditions.append(Finding.hostname == value)
            elif key == "program_name":
                continue
            elif key == "ip":
                conditions.append(IP.ip_address == value)
                needs_ip_join = True
            elif key == "$regex":
                if isinstance(value, dict):
                    pattern = value.get("$regex", "")
                    options = value.get("$options", "")
                    if pattern:
                        if "i" in options:
                            conditions.append(Finding.hostname.ilike(f"%{pattern}%"))
                        else:
                            conditions.append(Finding.hostname.like(f"%{pattern}%"))

        return conditions, needs_ip_join

    @staticmethod
    def _apply_nuclei_filters(query, filters: Dict[str, Any]):
        """Apply MongoDB-style filters to a nuclei (unified) query."""
        if not filters:
            return query
        conditions, needs_ip_join = FindingsRepository._nuclei_build_conditions(filters)
        if needs_ip_join:
            query = query.join(IP, Finding.ip_id == IP.id)
        if conditions:
            return query.filter(and_(*conditions))
        return query

    @staticmethod
    async def get_nuclei_by_id(finding_id: str) -> Optional[Dict[str, Any]]:
        async with get_db_session() as db:
            try:
                f = (
                    db.query(Finding)
                    .filter(
                        Finding.id == finding_id,
                        Finding.source == SOURCE_NUCLEI,
                    )
                    .first()
                )
                if not f:
                    return None
                return _nuclei_dict_from_finding(f)
            except Exception as e:
                logger.error(f"Error getting nuclei finding {finding_id}: {str(e)}")
                raise

    @staticmethod
    async def execute_nuclei_query(
        query: Dict[str, Any],
        limit: int =1000000,
        skip: int = 0,
        sort: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        async with get_db_session() as db:
            try:
                if QueryFilterUtils.handle_empty_program_filter(query):
                    return []
                sql_query = db.query(Finding).filter(FindingsRepository._nuclei_source_filter())
                sql_query = FindingsRepository.apply_program_access_filter(sql_query, query, Program)
                sql_query = FindingsRepository._apply_nuclei_filters(sql_query, query)
                if sort:
                    for field, direction in sort.items():
                        col = getattr(Finding, field, None)
                        if col is not None:
                            sql_query = sql_query.order_by(
                                asc(col) if direction == 1 else desc(col)
                            )
                sql_query = sql_query.offset(skip).limit(limit)
                findings = sql_query.all()
                return [
                    {
                        "id": str(f.id),
                        "url": f.url,
                        "template_id": (f.details or {}).get("template_id"),
                        "name": f.title,
                        "severity": f.severity,
                        "type": (f.details or {}).get("type"),
                        "hostname": f.hostname,
                        "ip": f.ip.ip_address if f.ip else None,
                        "program_name": f.program.name if f.program else None,
                        "matched_at": (f.details or {}).get("matched_at"),
                        "created_at": f.created_at.isoformat() if f.created_at else None,
                        **_finding_asset_ids_dict(f),
                    }
                    for f in findings
                ]
            except Exception as e:
                logger.error(f"Error executing nuclei query: {str(e)}")
                raise

    @staticmethod
    async def get_nuclei_query_count(query: Dict[str, Any]) -> int:
        async with get_db_session() as db:
            try:
                if QueryFilterUtils.handle_empty_program_filter(query):
                    return 0
                sql_query = db.query(func.count(Finding.id)).filter(
                    FindingsRepository._nuclei_source_filter()
                )
                sql_query = FindingsRepository.apply_program_access_filter(sql_query, query, Program)
                sql_query = FindingsRepository._apply_nuclei_filters(sql_query, query)
                return sql_query.scalar() or 0
            except Exception as e:
                logger.error(f"Error getting nuclei query count: {str(e)}")
                raise

    @staticmethod
    async def get_nuclei_stats_by_severity(query: Dict[str, Any]) -> Dict[str, int]:
        async with get_db_session() as db:
            try:
                stats = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
                for severity in stats.keys():
                    severity_query = db.query(Finding).filter(
                        and_(
                            FindingsRepository._nuclei_source_filter(),
                            Finding.severity == severity,
                        )
                    )
                    severity_query = FindingsRepository._apply_nuclei_filters(severity_query, query)
                    stats[severity] = severity_query.count()
                return stats
            except Exception as e:
                logger.error(f"Error getting nuclei stats: {str(e)}")
                raise

    @staticmethod
    async def get_distinct_nuclei_values_typed(
        field_name: str, programs: Optional[List[str]] = None
    ) -> List[str]:
        async with get_db_session() as db:
            try:
                base = (
                    db.query(Finding)
                    .join(Program)
                    .filter(Finding.source == SOURCE_NUCLEI)
                )
                if programs:
                    base = base.filter(Program.name.in_(programs))
                dt = FindingsRepository._detail_text

                if field_name == "name":
                    values = base.with_entities(Finding.title).distinct().all()
                elif field_name == "tags":
                    base = base.filter(Finding.details["tags"].isnot(None))
                    values = base.with_entities(
                        func.jsonb_array_elements_text(Finding.details["tags"])
                    ).distinct().all()
                elif field_name == "template_id":
                    values = base.with_entities(dt(Finding.details, "template_id")).distinct().all()
                elif field_name == "severity":
                    values = base.with_entities(Finding.severity).distinct().all()
                elif field_name == "hostname":
                    values = base.with_entities(Finding.hostname).distinct().all()
                elif field_name == "matcher_name":
                    values = base.with_entities(dt(Finding.details, "matcher_name")).distinct().all()
                elif field_name == "program_name":
                    values = base.with_entities(Program.name).distinct().all()
                elif field_name == "extracted_results":
                    base = base.filter(
                        Finding.details["extracted_results"].isnot(None),
                    )
                    values = base.with_entities(
                        func.jsonb_array_elements_text(Finding.details["extracted_results"])
                    ).distinct().all()
                else:
                    raise ValueError(f"Unsupported field: {field_name}")

                result = []
                for v in values:
                    if v[0] is not None:
                        val_str = str(v[0]).strip()
                        if (
                            val_str
                            and val_str != "[]"
                            and not (val_str.startswith("[") and val_str.endswith("]"))
                        ):
                            result.append(val_str)
                return sorted(result)
            except Exception as e:
                logger.error(f"Error getting typed distinct nuclei values: {str(e)}")
                raise

    @staticmethod
    async def search_nuclei_typed(
        *,
        search: Optional[str] = None,
        exact_match: Optional[str] = None,
        severity: Optional[str] = None,
        tags: Optional[str] = None,
        tags_include: Optional[List[str]] = None,
        tags_exclude: Optional[List[str]] = None,
        template_contains: Optional[str] = None,
        template_exact: Optional[str] = None,
        hostname_contains: Optional[str] = None,
        url_contains: Optional[str] = None,
        extracted_results_exact: Optional[str] = None,
        extracted_results_contains: Optional[str] = None,
        url_id: Optional[str] = None,
        subdomain_id: Optional[str] = None,
        ip_id: Optional[str] = None,
        service_id: Optional[str] = None,
        certificate_id: Optional[str] = None,
        apex_domain: Optional[str] = None,
        programs: Optional[List[str]] = None,
        sort_by: str = "created_at",
        sort_dir: str = "desc",
        limit: int = 25,
        skip: int = 0,
    ) -> Dict[str, Any]:
        dt = FindingsRepository._detail_text
        async with get_db_session() as db:
            try:
                base_query = (
                    db.query(
                        Finding.id.label("id"),
                        Finding.url.label("url"),
                        dt(Finding.details, "template_id").label("template_id"),
                        Finding.title.label("name"),
                        Finding.severity.label("severity"),
                        Finding.details["tags"].label("tags"),
                        dt(Finding.details, "type").label("type"),
                        Finding.hostname.label("hostname"),
                        dt(Finding.details, "matcher_name").label("matcher_name"),
                        Program.name.label("program_name"),
                        Finding.details["extracted_results"].label("extracted_results"),
                        dt(Finding.details, "matched_at").label("matched_at"),
                        Finding.created_at.label("created_at"),
                        Finding.updated_at.label("updated_at"),
                    )
                    .select_from(Finding)
                    .join(Program, Program.id == Finding.program_id)
                    .filter(Finding.source == SOURCE_NUCLEI)
                )

                def _apply_list_filters(q):
                    if programs is not None and len(programs) > 0:
                        q = q.filter(Program.name.in_(programs))
                    if search:
                        q = q.filter(Finding.title.ilike(f"%{search}%"))
                    if exact_match:
                        q = q.filter(Finding.title == exact_match)
                    if severity:
                        q = q.filter(Finding.severity == severity)
                    if tags:
                        q = q.filter(Finding.details.contains({"tags": [tags]}))
                    if tags_include and len(tags_include) > 0:
                        q = q.filter(
                            or_(*[Finding.details.contains({"tags": [t]}) for t in tags_include])
                        )
                    if tags_exclude and len(tags_exclude) > 0:
                        q = q.filter(
                            ~or_(*[Finding.details.contains({"tags": [t]}) for t in tags_exclude])
                        )
                    if template_contains:
                        q = q.filter(dt(Finding.details, "template_id").ilike(f"%{template_contains}%"))
                    if template_exact:
                        q = q.filter(dt(Finding.details, "template_id") == template_exact)
                    if hostname_contains:
                        q = q.filter(Finding.hostname.ilike(f"%{hostname_contains}%"))
                    if url_contains:
                        q = q.filter(Finding.url.ilike(f"%{url_contains}%"))
                    if extracted_results_exact:
                        q = q.filter(
                            Finding.details.contains({"extracted_results": [extracted_results_exact]})
                        )
                    if extracted_results_contains:
                        q = q.filter(
                            cast(Finding.details["extracted_results"], Text).ilike(
                                f"%{extracted_results_contains}%"
                            )
                        )
                    q = _apply_finding_asset_fk_filters(
                        q,
                        url_id=url_id,
                        subdomain_id=subdomain_id,
                        ip_id=ip_id,
                        service_id=service_id,
                        certificate_id=certificate_id,
                        apex_domain=apex_domain,
                    )
                    return q

                base_query = _apply_list_filters(base_query)

                count_query = (
                    db.query(func.count())
                    .select_from(Finding)
                    .join(Program, Program.id == Finding.program_id)
                    .filter(Finding.source == SOURCE_NUCLEI)
                )
                count_query = _apply_list_filters(count_query)
                total_count = count_query.scalar() or 0

                severity_query = (
                    db.query(Finding.severity, func.count(Finding.id).label("count"))
                    .select_from(Finding)
                    .join(Program, Program.id == Finding.program_id)
                    .filter(Finding.source == SOURCE_NUCLEI)
                )
                severity_query = _apply_list_filters(severity_query)
                severity_query = severity_query.group_by(Finding.severity)
                severity_distribution = {row.severity: row.count for row in severity_query.all()}

                sort_dir_func = asc if sort_dir == "asc" else desc
                sort_map = {
                    "name": Finding.title,
                    "severity": Finding.severity,
                    "tags": Finding.details["tags"],
                    "template_id": dt(Finding.details, "template_id"),
                    "hostname": Finding.hostname,
                    "url": Finding.url,
                    "program_name": Program.name,
                    "created_at": Finding.created_at,
                    "updated_at": Finding.updated_at,
                }
                sort_col = sort_map.get(sort_by, Finding.created_at)
                base_query = base_query.order_by(sort_dir_func(sort_col))
                base_query = base_query.offset(skip).limit(limit)
                rows = base_query.all()

                items: List[Dict[str, Any]] = []
                for row in rows:
                    items.append(
                        {
                            "id": str(row.id),
                            "url": row.url,
                            "tags": _jsonb_list(row.tags),
                            "template_id": row.template_id,
                            "name": row.name,
                            "severity": row.severity,
                            "type": row.type,
                            "hostname": row.hostname,
                            "matcher_name": row.matcher_name,
                            "program_name": row.program_name,
                            "extracted_results": row.extracted_results
                            if isinstance(row.extracted_results, list)
                            else (row.extracted_results or []),
                            "matched_at": row.matched_at,
                            "created_at": row.created_at.isoformat() if row.created_at else None,
                            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                        }
                    )
                return {
                    "items": items,
                    "total_count": total_count,
                    "severity_distribution": severity_distribution,
                }
            except Exception as e:
                logger.error(f"Error executing typed nuclei search: {str(e)}")
                raise

    @staticmethod
    async def update_nuclei_finding(finding_id: str, update_data: Dict[str, Any]) -> bool:
        detail_keys = {
            "template_id",
            "template_url",
            "template_path",
            "type",
            "matched_at",
            "matcher_name",
            "matched_line",
            "extracted_results",
            "info",
            "protocol",
            "tags",
            "status",
        }
        common_map = {
            "name": "title",
            "severity": "severity",
            "description": "description",
            "url": "url",
            "hostname": "hostname",
            "port": "port",
            "scheme": "scheme",
            "notes": "notes",
        }
        async with get_db_session() as db:
            try:
                f = (
                    db.query(Finding)
                    .filter(Finding.id == finding_id, Finding.source == SOURCE_NUCLEI)
                    .first()
                )
                if not f:
                    return False
                merged = dict(f.details or {})
                changed = False
                for raw_key, value in update_data.items():
                    key = "info" if raw_key == "info_data" else raw_key
                    if key in ("assigned_to",):
                        continue
                    if key in common_map and value is not None:
                        setattr(f, common_map[key], value)
                        changed = True
                    elif key in detail_keys:
                        if merged.get(key) != value:
                            merged[key] = value
                            changed = True
                if changed:
                    f.details = merged
                    f.updated_at = utcnow()
                db.commit()
                return True
            except Exception as e:
                db.rollback()
                logger.error(f"Error updating nuclei finding {finding_id}: {str(e)}")
                raise

    @staticmethod
    async def delete_nuclei_finding(finding_id: str) -> bool:
        async with get_db_session() as db:
            try:
                f = (
                    db.query(Finding)
                    .filter(Finding.id == finding_id, Finding.source == SOURCE_NUCLEI)
                    .first()
                )
                if not f:
                    return False
                db.delete(f)
                db.commit()
                return True
            except Exception as e:
                db.rollback()
                logger.error(f"Error deleting nuclei finding {finding_id}: {str(e)}")
                raise

    @staticmethod
    async def delete_nuclei_findings_batch(finding_ids: List[str]) -> Dict[str, Any]:
        async with get_db_session() as db:
            try:
                deleted_count = 0
                for fid in finding_ids:
                    f = (
                        db.query(Finding)
                        .filter(
                            Finding.id == fid,
                            Finding.source == SOURCE_NUCLEI,
                        )
                        .first()
                    )
                    if f:
                        db.delete(f)
                        deleted_count += 1
                db.commit()
                return {
                    "deleted_count": deleted_count,
                    "requested_count": len(finding_ids),
                    "failed_count": len(finding_ids) - deleted_count,
                }
            except Exception as e:
                db.rollback()
                logger.error(f"Error batch deleting nuclei findings: {str(e)}")
                raise

    # ----- WPScan -----

    @staticmethod
    async def create_or_update_wpscan_finding(finding_data: Dict[str, Any]) -> tuple[str, str]:
        async with get_db_session() as db:
            try:
                program = resolve_program_from_payload(db, finding_data)
                if finding_data.get("url"):
                    finding_data["url"] = _normalize_finding_url(finding_data.get("url"))
                if finding_data.get("hostname"):
                    finding_data["hostname"] = normalize_hostname(str(finding_data["hostname"]))
                if finding_data.get("scheme") and isinstance(finding_data["scheme"], str):
                    finding_data["scheme"] = finding_data["scheme"].lower()

                fp = fingerprint_wpscan(
                    url=finding_data.get("url"),
                    item_name=finding_data.get("item_name"),
                    program_id=program.id,
                )
                existing = (
                    db.query(Finding)
                    .filter(
                        and_(
                            Finding.program_id == program.id,
                            Finding.source == SOURCE_WPSCAN,
                            Finding.fingerprint == fp,
                        )
                    )
                    .first()
                )
                details = _wpscan_payload_to_details(finding_data)

                finding_url = (
                    finding_data.get("url")
                    if "url" in finding_data
                    else (existing.url if existing else None)
                )
                finding_scheme = (
                    finding_data.get("scheme")
                    if "scheme" in finding_data
                    else (existing.scheme if existing else None)
                )
                resolved = await resolve_finding_asset_ids_with_url_ensure(
                    db,
                    program.id,
                    finding_data.get("program_name") or program.name,
                    url=finding_url,
                    hostname=finding_data.get("hostname")
                    if "hostname" in finding_data
                    else (existing.hostname if existing else None),
                    port=finding_data.get("port")
                    if "port" in finding_data
                    else (existing.port if existing else None),
                    scheme=finding_scheme,
                    resolve_subdomain=False,
                    resolve_ip=False,
                    resolve_service=False,
                )

                if existing:
                    updated = False
                    if "severity" in finding_data and finding_data.get("severity") != existing.severity:
                        existing.severity = finding_data["severity"]
                        updated = True
                    if "description" in finding_data and finding_data.get("description") != existing.description:
                        existing.description = finding_data.get("description")
                        updated = True
                    if "title" in finding_data and finding_data.get("title") != existing.title:
                        existing.title = finding_data.get("title")
                        updated = True
                    if "notes" in finding_data and finding_data.get("notes") != existing.notes:
                        existing.notes = finding_data.get("notes")
                        updated = True
                    for k, v in details.items():
                        if v is None and k not in ("references", "cve_ids", "status"):
                            continue
                        if (existing.details or {}).get(k) != v:
                            merged = dict(existing.details or {})
                            merged[k] = v
                            existing.details = merged
                            updated = True
                    for col, val in (
                        ("url", finding_data.get("url")),
                        ("hostname", finding_data.get("hostname")),
                        ("port", finding_data.get("port")),
                        ("scheme", finding_data.get("scheme")),
                    ):
                        if val is not None and getattr(existing, col) != val:
                            setattr(existing, col, val)
                            updated = True
                    if _apply_resolved_assets_to_finding(
                        existing,
                        resolved,
                        apply_subdomain=False,
                        apply_ip=False,
                        apply_service=False,
                    ):
                        updated = True
                    if updated:
                        existing.updated_at = utcnow()
                    db.commit()
                    return str(existing.id), "updated" if updated else "skipped"

                row = Finding(
                    id=uuid.uuid4(),
                    program_id=program.id,
                    source=SOURCE_WPSCAN,
                    fingerprint=fp,
                    title=finding_data.get("title"),
                    description=finding_data.get("description"),
                    severity=finding_data.get("severity"),
                    url=finding_data.get("url"),
                    hostname=finding_data.get("hostname"),
                    port=finding_data.get("port"),
                    scheme=finding_data.get("scheme"),
                    url_id=resolved.url_id,
                    observed_at=utcnow(),
                    notes=finding_data.get("notes"),
                    details=details,
                )
                db.add(row)
                db.commit()
                db.refresh(row)
                try:
                    await publisher.publish(
                        "events.findings.created.wpscan",
                        {
                            "event": "finding.created",
                            "type": "wpscan",
                            "program_name": finding_data.get("program_name"),
                            "record_id": str(row.id),
                            "severity": finding_data.get("severity"),
                            "item_name": finding_data.get("item_name"),
                            "item_type": finding_data.get("item_type"),
                            "url": finding_data.get("url"),
                        },
                    )
                except Exception:
                    pass
                return str(row.id), "created"
            except Exception as e:
                db.rollback()
                logger.error(f"Error creating/updating WPScan finding: {str(e)}")
                raise

    @staticmethod
    async def get_wpscan_by_id(finding_id: str) -> Optional[Dict[str, Any]]:
        async with get_db_session() as db:
            try:
                f = (
                    db.query(Finding)
                    .filter(Finding.id == finding_id, Finding.source == SOURCE_WPSCAN)
                    .first()
                )
                if not f:
                    return None
                return _wpscan_dict_from_finding(f)
            except Exception as e:
                logger.error(f"Error getting WPScan finding {finding_id}: {str(e)}")
                raise

    @staticmethod
    def _wpscan_build_conditions(filters: Dict[str, Any]) -> List[Any]:
        conditions: List[Any] = []
        dt = FindingsRepository._detail_text
        if not filters:
            return conditions
        for key, value in filters.items():
            if key == "$and":
                groups = []
                for sub in value:
                    sub_conds = FindingsRepository._wpscan_build_conditions(sub)
                    if sub_conds:
                        groups.append(and_(*sub_conds))
                if groups:
                    conditions.append(and_(*groups))
            elif key == "$or":
                groups = []
                for sub in value:
                    sub_conds = FindingsRepository._wpscan_build_conditions(sub)
                    if sub_conds:
                        groups.append(and_(*sub_conds))
                if groups:
                    conditions.append(or_(*groups))
            elif key == "severity":
                conditions.append(Finding.severity == value)
            elif key == "item_name":
                if isinstance(value, dict) and "$regex" in value:
                    pattern = value.get("$regex", "")
                    options = value.get("$options", "")
                    if "i" in options:
                        conditions.append(dt(Finding.details, "item_name").ilike(f"%{pattern}%"))
                    else:
                        conditions.append(dt(Finding.details, "item_name").like(f"%{pattern}%"))
                else:
                    conditions.append(dt(Finding.details, "item_name") == value)
            elif key == "item_type":
                conditions.append(dt(Finding.details, "item_type") == value)
            elif key == "hostname":
                conditions.append(Finding.hostname == value)
            elif key == "program_name":
                continue
        return conditions

    @staticmethod
    def _apply_wpscan_filters(query, filters: Dict[str, Any]):
        if not filters:
            return query
        conditions = FindingsRepository._wpscan_build_conditions(filters)
        if conditions:
            return query.filter(and_(*conditions))
        return query

    @staticmethod
    async def get_wpscan_query_count(query: Dict[str, Any]) -> int:
        async with get_db_session() as db:
            try:
                if QueryFilterUtils.handle_empty_program_filter(query):
                    return 0
                sql_query = db.query(func.count(Finding.id)).filter(
                    FindingsRepository._wpscan_source_filter()
                )
                sql_query = FindingsRepository.apply_program_access_filter(sql_query, query, Program)
                sql_query = FindingsRepository._apply_wpscan_filters(sql_query, query)
                return sql_query.scalar() or 0
            except Exception as e:
                logger.error(f"Error getting WPScan query count: {str(e)}")
                raise

    @staticmethod
    async def get_wpscan_stats_by_severity(query: Dict[str, Any]) -> Dict[str, int]:
        async with get_db_session() as db:
            try:
                stats = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
                for severity in stats.keys():
                    severity_query = db.query(Finding).filter(
                        and_(
                            FindingsRepository._wpscan_source_filter(),
                            Finding.severity == severity,
                        )
                    )
                    severity_query = FindingsRepository._apply_wpscan_filters(severity_query, query)
                    stats[severity] = severity_query.count()
                return stats
            except Exception as e:
                logger.error(f"Error getting WPScan stats: {str(e)}")
                raise

    @staticmethod
    async def get_distinct_wpscan_values_typed(
        field_name: str, programs: Optional[List[str]] = None
    ) -> List[str]:
        dt = FindingsRepository._detail_text
        async with get_db_session() as db:
            try:
                base = (
                    db.query(Finding)
                    .join(Program)
                    .filter(Finding.source == SOURCE_WPSCAN)
                )
                if programs:
                    base = base.filter(Program.name.in_(programs))
                if field_name == "item_name":
                    values = base.with_entities(dt(Finding.details, "item_name")).distinct().all()
                elif field_name == "item_type":
                    values = base.with_entities(dt(Finding.details, "item_type")).distinct().all()
                elif field_name == "severity":
                    values = base.with_entities(Finding.severity).distinct().all()
                elif field_name == "hostname":
                    values = base.with_entities(Finding.hostname).distinct().all()
                elif field_name == "vulnerability_type":
                    values = base.with_entities(dt(Finding.details, "vulnerability_type")).distinct().all()
                elif field_name == "program_name":
                    values = base.with_entities(Program.name).distinct().all()
                elif field_name == "cve_ids":
                    base = base.filter(Finding.details["cve_ids"].isnot(None))
                    values = base.with_entities(
                        func.jsonb_array_elements_text(Finding.details["cve_ids"])
                    ).distinct().all()
                else:
                    raise ValueError(f"Unsupported field: {field_name}")
                result = []
                for v in values:
                    if v[0] is not None:
                        val_str = str(v[0]).strip()
                        if val_str and val_str != "[]":
                            result.append(val_str)
                return sorted(result)
            except Exception as e:
                logger.error(f"Error getting typed distinct WPScan values: {str(e)}")
                raise

    @staticmethod
    async def search_wpscan_typed(
        *,
        search: Optional[str] = None,
        exact_match: Optional[str] = None,
        severity: Optional[str] = None,
        item_type: Optional[str] = None,
        item_name_contains: Optional[str] = None,
        item_name_exact: Optional[str] = None,
        hostname_contains: Optional[str] = None,
        cve_ids_exact: Optional[str] = None,
        cve_ids_contains: Optional[str] = None,
        url_id: Optional[str] = None,
        subdomain_id: Optional[str] = None,
        ip_id: Optional[str] = None,
        service_id: Optional[str] = None,
        certificate_id: Optional[str] = None,
        apex_domain: Optional[str] = None,
        programs: Optional[List[str]] = None,
        sort_by: str = "created_at",
        sort_dir: str = "desc",
        limit: int = 25,
        skip: int = 0,
    ) -> Dict[str, Any]:
        dt = FindingsRepository._detail_text
        async with get_db_session() as db:
            try:
                base_query = (
                    db.query(
                        Finding.id.label("id"),
                        Finding.url.label("url"),
                        dt(Finding.details, "item_name").label("item_name"),
                        dt(Finding.details, "item_type").label("item_type"),
                        dt(Finding.details, "vulnerability_type").label("vulnerability_type"),
                        Finding.severity.label("severity"),
                        Finding.title.label("title"),
                        Finding.description.label("description"),
                        dt(Finding.details, "fixed_in").label("fixed_in"),
                        Finding.details["references"].label("references"),
                        Finding.details["cve_ids"].label("cve_ids"),
                        Finding.hostname.label("hostname"),
                        Program.name.label("program_name"),
                        Finding.created_at.label("created_at"),
                        Finding.updated_at.label("updated_at"),
                    )
                    .select_from(Finding)
                    .join(Program, Program.id == Finding.program_id)
                    .filter(Finding.source == SOURCE_WPSCAN)
                )

                def _apply_filters(q):
                    if programs is not None and len(programs) > 0:
                        q = q.filter(Program.name.in_(programs))
                    if search:
                        q = q.filter(
                            or_(
                                Finding.title.ilike(f"%{search}%"),
                                dt(Finding.details, "item_name").ilike(f"%{search}%"),
                                Finding.description.ilike(f"%{search}%"),
                            )
                        )
                    if exact_match:
                        q = q.filter(dt(Finding.details, "item_name") == exact_match)
                    if severity:
                        q = q.filter(Finding.severity == severity)
                    if item_type:
                        q = q.filter(dt(Finding.details, "item_type") == item_type)
                    if item_name_contains:
                        q = q.filter(dt(Finding.details, "item_name").ilike(f"%{item_name_contains}%"))
                    if item_name_exact:
                        q = q.filter(dt(Finding.details, "item_name") == item_name_exact)
                    if hostname_contains:
                        q = q.filter(Finding.hostname.ilike(f"%{hostname_contains}%"))
                    if cve_ids_exact:
                        q = q.filter(Finding.details["cve_ids"].contains([cve_ids_exact]))
                    if cve_ids_contains:
                        q = q.filter(
                            cast(Finding.details["cve_ids"], Text).ilike(f"%{cve_ids_contains}%")
                        )
                    q = _apply_finding_asset_fk_filters(
                        q,
                        url_id=url_id,
                        subdomain_id=subdomain_id,
                        ip_id=ip_id,
                        service_id=service_id,
                        certificate_id=certificate_id,
                        apex_domain=apex_domain,
                    )
                    return q

                base_query = _apply_filters(base_query)
                count_query = (
                    db.query(func.count())
                    .select_from(Finding)
                    .join(Program, Program.id == Finding.program_id)
                    .filter(Finding.source == SOURCE_WPSCAN)
                )
                count_query = _apply_filters(count_query)
                total_count = count_query.scalar() or 0

                severity_query = (
                    db.query(Finding.severity, func.count(Finding.id).label("count"))
                    .select_from(Finding)
                    .join(Program, Program.id == Finding.program_id)
                    .filter(Finding.source == SOURCE_WPSCAN)
                )
                severity_query = _apply_filters(severity_query)
                severity_query = severity_query.group_by(Finding.severity)
                severity_distribution = {row.severity: row.count for row in severity_query.all()}
                sort_dir_func = asc if sort_dir == "asc" else desc
                sort_map = {
                    "item_name": dt(Finding.details, "item_name"),
                    "item_type": dt(Finding.details, "item_type"),
                    "severity": Finding.severity,
                    "hostname": Finding.hostname,
                    "url": Finding.url,
                    "program_name": Program.name,
                    "created_at": Finding.created_at,
                    "updated_at": Finding.updated_at,
                }
                sort_col = sort_map.get(sort_by, Finding.created_at)
                base_query = base_query.order_by(sort_dir_func(sort_col)).offset(skip).limit(limit)
                rows = base_query.all()
                items = []
                for row in rows:
                    items.append(
                        {
                            "id": str(row.id),
                            "url": row.url,
                            "item_name": row.item_name,
                            "item_type": row.item_type,
                            "vulnerability_type": row.vulnerability_type,
                            "severity": row.severity,
                            "title": row.title,
                            "description": row.description,
                            "fixed_in": row.fixed_in,
                            "references": _jsonb_list(row.references),
                            "cve_ids": _jsonb_list(row.cve_ids),
                            "hostname": row.hostname,
                            "program_name": row.program_name,
                            "created_at": row.created_at.isoformat() if row.created_at else None,
                            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                        }
                    )
                return {
                    "items": items,
                    "total_count": total_count,
                    "severity_distribution": severity_distribution,
                }
            except Exception as e:
                logger.error(f"Error executing typed WPScan search: {str(e)}")
                raise

    @staticmethod
    async def update_wpscan_finding(finding_id: str, update_data: Dict[str, Any]) -> bool:
        detail_keys = {
            "item_name",
            "item_type",
            "vulnerability_type",
            "fixed_in",
            "enumeration_data",
            "status",
            "references",
            "cve_ids",
        }
        async with get_db_session() as db:
            try:
                f = (
                    db.query(Finding)
                    .filter(Finding.id == finding_id, Finding.source == SOURCE_WPSCAN)
                    .first()
                )
                if not f:
                    return False
                merged = dict(f.details or {})
                for key, value in update_data.items():
                    if key == "assigned_to":
                        continue
                    if key in ("title", "description", "severity", "url", "hostname", "port", "scheme", "notes"):
                        setattr(f, key, value)
                    elif key in detail_keys:
                        merged[key] = value
                f.details = merged
                f.updated_at = utcnow()
                db.commit()
                return True
            except Exception as e:
                db.rollback()
                logger.error(f"Error updating WPScan finding {finding_id}: {str(e)}")
                raise

    @staticmethod
    async def delete_wpscan_finding(finding_id: str) -> bool:
        async with get_db_session() as db:
            try:
                f = (
                    db.query(Finding)
                    .filter(Finding.id == finding_id, Finding.source == SOURCE_WPSCAN)
                    .first()
                )
                if not f:
                    return False
                db.delete(f)
                db.commit()
                return True
            except Exception as e:
                db.rollback()
                logger.error(f"Error deleting WPScan finding {finding_id}: {str(e)}")
                raise

    @staticmethod
    async def delete_wpscan_findings_batch(finding_ids: List[str]) -> Dict[str, Any]:
        async with get_db_session() as db:
            try:
                findings = (
                    db.query(Finding)
                    .filter(
                        Finding.id.in_(finding_ids),
                        Finding.source == SOURCE_WPSCAN,
                    )
                    .all()
                )
                deleted_count = 0
                for f in findings:
                    db.delete(f)
                    deleted_count += 1
                db.commit()
                return {
                    "deleted_count": deleted_count,
                    "not_found_count": len(finding_ids) - deleted_count,
                    "total_requested": len(finding_ids),
                }
            except Exception as e:
                db.rollback()
                logger.error(f"Error batch deleting WPScan findings: {str(e)}")
                raise

    @staticmethod
    async def execute_wpscan_query(
        query: Dict[str, Any],
        limit: int = 1000000,
        skip: int = 0,
        sort: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        async with get_db_session() as db:
            try:
                if QueryFilterUtils.handle_empty_program_filter(query):
                    return []
                sql_query = db.query(Finding).filter(FindingsRepository._wpscan_source_filter())
                sql_query = FindingsRepository.apply_program_access_filter(sql_query, query, Program)
                sql_query = FindingsRepository._apply_wpscan_filters(sql_query, query)
                if sort:
                    for field, direction in sort.items():
                        col = getattr(Finding, field, None)
                        if col is not None:
                            sql_query = sql_query.order_by(
                                asc(col) if direction == 1 else desc(col)
                            )
                sql_query = sql_query.offset(skip).limit(limit)
                findings = sql_query.all()
                dt = FindingsRepository._detail_text
                return [
                    {
                        "id": str(f.id),
                        "url": f.url,
                        "item_name": (f.details or {}).get("item_name"),
                        "item_type": (f.details or {}).get("item_type"),
                        "severity": f.severity,
                        "hostname": f.hostname,
                        "program_name": f.program.name if f.program else None,
                        "created_at": f.created_at.isoformat() if f.created_at else None,
                    }
                    for f in findings
                ]
            except Exception as e:
                logger.error(f"Error executing WPScan query: {str(e)}")
                raise

    # ----- Broken links -----

    @staticmethod
    def _broken_checked_at(finding_data: Dict[str, Any]):
        checked_at = finding_data.get("checked_at")
        if checked_at and isinstance(checked_at, str):
            return datetime.fromisoformat(checked_at.replace("Z", "+00:00")).replace(tzinfo=None)
        if isinstance(checked_at, datetime):
            return checked_at.replace(tzinfo=None) if checked_at.tzinfo else checked_at
        return utcnow()

    @staticmethod
    async def create_or_update_broken_link(finding_data: Dict[str, Any]) -> tuple[str, str]:
        async with get_db_session() as db:
            try:
                program = resolve_program_from_payload(db, finding_data)
                if finding_data.get("domain"):
                    finding_data["domain"] = normalize_hostname(str(finding_data["domain"]))
                if finding_data.get("url"):
                    finding_data["url"] = _normalize_finding_url(finding_data.get("url"))
                url = finding_data.get("url")
                fp = fingerprint_broken_link(program_id=program.id, url=url)
                existing = (
                    db.query(Finding)
                    .filter(
                        and_(
                            Finding.program_id == program.id,
                            Finding.source == SOURCE_BROKEN_LINK,
                            Finding.fingerprint == fp,
                        )
                    )
                    .first()
                )
                details = _broken_payload_to_details(finding_data)
                observed = FindingsRepository._broken_checked_at(finding_data)

                if existing:
                    updated = False
                    if "status" in finding_data and finding_data.get("status") != (existing.details or {}).get(
                        "status"
                    ):
                        merged = dict(existing.details or {})
                        merged["status"] = finding_data.get("status")
                        existing.details = merged
                        updated = True
                    if "url" in finding_data and finding_data.get("url") != existing.url:
                        existing.url = finding_data.get("url")
                        updated = True
                    for k, v in details.items():
                        if v is not None and (existing.details or {}).get(k) != v:
                            merged = dict(existing.details or {})
                            merged[k] = v
                            existing.details = merged
                            updated = True
                    if "notes" in finding_data and finding_data.get("notes") != existing.notes:
                        existing.notes = finding_data.get("notes")
                        updated = True
                    if updated:
                        existing.observed_at = observed
                        existing.updated_at = utcnow()
                    db.commit()
                    return str(existing.id), "updated" if updated else "skipped"

                row = Finding(
                    id=uuid.uuid4(),
                    program_id=program.id,
                    source=SOURCE_BROKEN_LINK,
                    fingerprint=fp,
                    title=None,
                    description=finding_data.get("reason"),
                    severity=None,
                    url=finding_data.get("url"),
                    hostname=finding_data.get("domain"),
                    port=None,
                    scheme=None,
                    ip_id=None,
                    observed_at=observed,
                    notes=finding_data.get("notes"),
                    details=details,
                )
                db.add(row)
                db.commit()
                db.refresh(row)
                try:
                    await publisher.publish(
                        "events.findings.created.broken_link",
                        {
                            "event": "finding.created",
                            "type": "broken_link",
                            "program_name": finding_data.get("program_name"),
                            "record_id": str(row.id),
                            "link_type": finding_data.get("link_type", "social_media"),
                            "media_type": finding_data.get("media_type"),
                            "domain": finding_data.get("domain"),
                            "reason": finding_data.get("reason"),
                            "status": finding_data.get("status"),
                        },
                    )
                except Exception:
                    pass
                return str(row.id), "created"
            except Exception as e:
                db.rollback()
                logger.error(f"Error creating/updating broken link finding: {str(e)}")
                raise

    @staticmethod
    async def get_broken_link_by_id(finding_id: str) -> Optional[Dict[str, Any]]:
        async with get_db_session() as db:
            try:
                f = (
                    db.query(Finding)
                    .filter(Finding.id == finding_id, Finding.source == SOURCE_BROKEN_LINK)
                    .first()
                )
                if not f:
                    return None
                return _broken_dict_from_finding(f)
            except Exception as e:
                logger.error(f"Error getting broken link finding {finding_id}: {str(e)}")
                raise

    @staticmethod
    async def search_broken_links(
        program_name: Optional[str] = None,
        link_type: Optional[str] = None,
        media_type: Optional[str] = None,
        status: Optional[str] = None,
        domain_search: Optional[str] = None,
        sort_by: str = "checked_at",
        sort_dir: str = "desc",
        page: int = 1,
        page_size: int = 25,
    ) -> Dict[str, Any]:
        dt = FindingsRepository._detail_text
        async with get_db_session() as db:
            try:
                query = (
                    db.query(Finding)
                    .join(Program)
                    .filter(Finding.source == SOURCE_BROKEN_LINK)
                )
                if program_name:
                    query = query.filter(Program.name == program_name)
                if link_type:
                    query = query.filter(dt(Finding.details, "link_type") == link_type)
                if media_type:
                    query = query.filter(dt(Finding.details, "media_type") == media_type)
                if status:
                    query = query.filter(dt(Finding.details, "status") == status)
                if domain_search:
                    query = query.filter(dt(Finding.details, "domain").ilike(f"%{domain_search}%"))
                sort_map = {
                    "checked_at": Finding.observed_at,
                    "created_at": Finding.created_at,
                    "updated_at": Finding.updated_at,
                    "status": dt(Finding.details, "status"),
                    "url": Finding.url,
                }
                sort_field = sort_map.get(sort_by, Finding.observed_at)
                query = query.order_by(asc(sort_field) if sort_dir.lower() == "asc" else desc(sort_field))
                total_count = query.count()
                offset = (page - 1) * page_size
                findings = query.offset(offset).limit(page_size).all()
                result = [_broken_dict_from_finding(f) for f in findings]
                return {
                    "findings": result,
                    "total": total_count,
                    "page": page,
                    "page_size": page_size,
                    "total_pages": (total_count + page_size - 1) // page_size,
                }
            except Exception as e:
                logger.error(f"Error searching broken links: {str(e)}")
                raise

    @staticmethod
    async def update_broken_link(
        finding_id: str, update_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        async with get_db_session() as db:
            try:
                f = (
                    db.query(Finding)
                    .filter(Finding.id == finding_id, Finding.source == SOURCE_BROKEN_LINK)
                    .first()
                )
                if not f:
                    return None
                merged = dict(f.details or {})
                if "status" in update_data:
                    merged["status"] = update_data["status"]
                if "error_code" in update_data:
                    merged["error_code"] = update_data["error_code"]
                if "response_data" in update_data:
                    merged["response_data"] = update_data["response_data"]
                if "checked_at" in update_data and update_data["checked_at"]:
                    checked_at = update_data["checked_at"]
                    if isinstance(checked_at, str):
                        checked_at = datetime.fromisoformat(checked_at.replace("Z", "+00:00"))
                    merged["checked_at"] = checked_at
                    f.observed_at = checked_at.replace(tzinfo=None) if getattr(checked_at, "tzinfo", None) else checked_at
                if "notes" in update_data:
                    f.notes = update_data["notes"]
                f.details = merged
                f.updated_at = utcnow()
                db.commit()
                db.refresh(f)
                return await FindingsRepository.get_broken_link_by_id(finding_id)
            except Exception as e:
                db.rollback()
                logger.error(f"Error updating broken link finding {finding_id}: {str(e)}")
                raise

    @staticmethod
    async def delete_broken_link(finding_id: str) -> bool:
        async with get_db_session() as db:
            try:
                f = (
                    db.query(Finding)
                    .filter(Finding.id == finding_id, Finding.source == SOURCE_BROKEN_LINK)
                    .first()
                )
                if not f:
                    return False
                db.delete(f)
                db.commit()
                return True
            except Exception as e:
                db.rollback()
                logger.error(f"Error deleting broken link finding {finding_id}: {str(e)}")
                raise

    @staticmethod
    async def delete_broken_links_batch(finding_ids: List[str]) -> Dict[str, Any]:
        async with get_db_session() as db:
            try:
                findings = (
                    db.query(Finding)
                    .filter(
                        Finding.id.in_(finding_ids),
                        Finding.source == SOURCE_BROKEN_LINK,
                    )
                    .all()
                )
                deleted_count = 0
                for f in findings:
                    db.delete(f)
                    deleted_count += 1
                found_ids = {str(f.id) for f in findings}
                not_found_ids = [fid for fid in finding_ids if fid not in found_ids]
                db.commit()
                return {"deleted_count": deleted_count, "not_found_ids": not_found_ids}
            except Exception as e:
                db.rollback()
                logger.error(f"Error batch deleting broken link findings: {str(e)}")
                raise

    @staticmethod
    def _get_broken_links_stats_sync(
        program_name: Optional[str] = None,
        restrict_to_program_names: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        db = SessionLocal()
        dt = FindingsRepository._detail_text
        try:
            q = (
                db.query(
                    func.count(Finding.id),
                    func.count().filter(dt(Finding.details, "status") == "valid"),
                    func.count().filter(dt(Finding.details, "status") == "broken"),
                    func.count().filter(dt(Finding.details, "status") == "error"),
                    func.count().filter(dt(Finding.details, "status") == "throttled"),
                    func.count().filter(dt(Finding.details, "media_type") == "facebook"),
                    func.count().filter(dt(Finding.details, "media_type") == "instagram"),
                    func.count().filter(dt(Finding.details, "media_type") == "twitter"),
                    func.count().filter(dt(Finding.details, "media_type") == "x"),
                    func.count().filter(dt(Finding.details, "media_type") == "linkedin"),
                )
                .select_from(Finding)
                .join(Program, Finding.program_id == Program.id)
                .filter(Finding.source == SOURCE_BROKEN_LINK)
            )
            if program_name:
                q = q.filter(Program.name == program_name)
            elif restrict_to_program_names is not None:
                if len(restrict_to_program_names) == 0:
                    return {
                        "total": 0,
                        "valid": 0,
                        "broken": 0,
                        "error": 0,
                        "throttled": 0,
                        "by_media_type": {},
                    }
                q = q.filter(Program.name.in_(restrict_to_program_names))
            row = q.one()
            labels = ["facebook", "instagram", "twitter", "x", "linkedin"]
            by_media_type: Dict[str, int] = {}
            for i, lab in enumerate(labels):
                c = int(row[5 + i] or 0)
                if c > 0:
                    by_media_type[lab] = c
            return {
                "total": int(row[0] or 0),
                "valid": int(row[1] or 0),
                "broken": int(row[2] or 0),
                "error": int(row[3] or 0),
                "throttled": int(row[4] or 0),
                "by_media_type": by_media_type,
            }
        except Exception as exc:
            logger.error("Error getting broken links stats: %s", exc)
            raise
        finally:
            db.close()

    @staticmethod
    async def get_broken_links_stats(
        program_name: Optional[str] = None,
        restrict_to_program_names: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        return await run_in_threadpool(
            FindingsRepository._get_broken_links_stats_sync,
            program_name,
            restrict_to_program_names,
        )
