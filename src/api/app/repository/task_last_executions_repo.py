"""Repository for task_last_executions (runner last-execution scheduling)."""

from __future__ import annotations

import logging
import uuid as uuid_mod
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from sqlalchemy import and_, asc, desc, func, or_, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, joinedload

from db import get_db_session
from models.base import utcnow
from models.postgres import (
    ApexDomain,
    Certificate,
    IP,
    Service,
    Subdomain,
    SubdomainIP,
    TaskLastExecution,
    URL,
)
from repository.task_history_repo import (
    normalize_target_key,
    resolve_target_strings_to_asset_pairs,
)
from utils.task_params_fingerprint import params_fingerprint

logger = logging.getLogger(__name__)

_ASSET_TYPE_ALIASES = {
    "subdomain": "subdomain",
    "ip": "ip",
    "url": "url",
    "apex-domain": "apex_domain",
    "apex_domain": "apex_domain",
    "service": "service",
    "certificate": "certificate",
}


def normalize_asset_type(asset_type: str) -> str:
    key = (asset_type or "").strip().lower().replace("-", "_")
    if key == "apexdomain":
        key = "apex_domain"
    normalized = _ASSET_TYPE_ALIASES.get(key) or _ASSET_TYPE_ALIASES.get(asset_type)
    if not normalized:
        raise ValueError(f"Unsupported asset type: {asset_type}")
    return normalized


_PROMOTABLE_ASSET_TYPES = frozenset({"subdomain", "apex_domain", "ip", "url"})


def canonical_keys_for_asset(asset_type: str, asset_payload: Dict[str, Any]) -> List[str]:
    """Derive normalized target_key lookup strings for an ingested asset event."""
    try:
        normalized = normalize_asset_type(asset_type)
    except ValueError:
        return []
    if normalized not in _PROMOTABLE_ASSET_TYPES:
        return []

    keys: Set[str] = set()
    if normalized in ("subdomain", "apex_domain"):
        name = asset_payload.get("name")
        if name:
            key = normalize_target_key(str(name))
            if key:
                keys.add(key)
    elif normalized == "ip":
        for field in ("ip_address", "ip"):
            val = asset_payload.get(field)
            if val:
                key = normalize_target_key(str(val))
                if key:
                    keys.add(key)
    elif normalized == "url":
        url_val = asset_payload.get("url")
        if url_val:
            key = normalize_target_key(str(url_val))
            if key:
                keys.add(key)
    return sorted(keys)


def build_promotion_entry(
    event: Dict[str, Any],
    *,
    fallback_asset_type: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Build a promotion entry from an asset ingest event dict."""
    asset_type = event.get("asset_type") or fallback_asset_type
    record_id = event.get("record_id")
    if not asset_type or not record_id:
        return None
    try:
        normalized_type = normalize_asset_type(str(asset_type))
    except ValueError:
        return None
    if normalized_type not in _PROMOTABLE_ASSET_TYPES:
        return None
    try:
        asset_id = uuid_mod.UUID(str(record_id))
    except ValueError:
        return None
    target_keys = canonical_keys_for_asset(normalized_type, event)
    if not target_keys:
        return None
    return {
        "asset_type": normalized_type,
        "asset_id": asset_id,
        "target_keys": target_keys,
    }


class TaskLastExecutionsRepository:
    @staticmethod
    def upsert_success_sync(
        db: Session,
        *,
        program_id: uuid_mod.UUID,
        task_type: str,
        asset_type: str,
        asset_id: uuid_mod.UUID,
        params_fingerprint: str,
        last_success_at: datetime,
    ) -> None:
        stmt = insert(TaskLastExecution).values(
            program_id=program_id,
            task_type=task_type,
            asset_type=asset_type,
            asset_id=asset_id,
            params_fingerprint=params_fingerprint,
            last_success_at=last_success_at,
            updated_at=utcnow(),
        )
        excluded = stmt.excluded
        stmt = stmt.on_conflict_do_update(
            index_elements=[
                "program_id",
                "task_type",
                "asset_type",
                "asset_id",
                "params_fingerprint",
            ],
            index_where=text("asset_id IS NOT NULL"),
            set_={
                "last_success_at": func.greatest(
                    TaskLastExecution.last_success_at,
                    excluded.last_success_at,
                ),
                "updated_at": func.now(),
            },
        )
        db.execute(stmt)

    @staticmethod
    def upsert_target_success_sync(
        db: Session,
        *,
        program_id: uuid_mod.UUID,
        task_type: str,
        target_key: str,
        params_fingerprint: str,
        last_success_at: datetime,
    ) -> None:
        stmt = insert(TaskLastExecution).values(
            program_id=program_id,
            task_type=task_type,
            asset_type="target",
            asset_id=None,
            target_key=target_key,
            params_fingerprint=params_fingerprint,
            last_success_at=last_success_at,
            updated_at=utcnow(),
        )
        excluded = stmt.excluded
        stmt = stmt.on_conflict_do_update(
            index_elements=["program_id", "task_type", "target_key", "params_fingerprint"],
            index_where=text("target_key IS NOT NULL"),
            set_={
                "last_success_at": func.greatest(
                    TaskLastExecution.last_success_at,
                    excluded.last_success_at,
                ),
                "updated_at": func.now(),
            },
        )
        db.execute(stmt)

    @staticmethod
    def upsert_target_successes_sync(db: Session, rows: Sequence[Dict[str, Any]]) -> None:
        for row in rows:
            task_type = row.get("task_type")
            target_key = row.get("target_key")
            completed = row.get("completed_at")
            if not task_type or not target_key or not isinstance(completed, datetime):
                continue
            task_params = row.get("task_params") or {}
            fp = params_fingerprint(str(task_type), task_params)
            TaskLastExecutionsRepository.upsert_target_success_sync(
                db,
                program_id=row["program_id"],
                task_type=str(task_type),
                target_key=str(target_key),
                params_fingerprint=fp,
                last_success_at=completed,
            )

    @staticmethod
    def upsert_successes_from_rows_sync(db: Session, rows: Sequence[Dict[str, Any]]) -> None:
        for row in rows:
            status = row.get("status")
            if not isinstance(status, str) or status.lower() != "success":
                continue
            task_type = row.get("task_type")
            if not task_type:
                continue
            completed = row.get("completed_at")
            if not isinstance(completed, datetime):
                continue
            task_params = row.get("task_params") or {}
            fp = params_fingerprint(str(task_type), task_params)
            TaskLastExecutionsRepository.upsert_success_sync(
                db,
                program_id=row["program_id"],
                task_type=str(task_type),
                asset_type=str(row["asset_type"]),
                asset_id=row["asset_id"],
                params_fingerprint=fp,
                last_success_at=completed,
            )

    @staticmethod
    async def upsert_successes_from_rows(rows: Sequence[Dict[str, Any]]) -> None:
        if not rows:
            return
        async with get_db_session() as db:
            TaskLastExecutionsRepository.upsert_successes_from_rows_sync(db, rows)
            db.commit()

    @staticmethod
    def promote_target_keys_batch_sync(
        db: Session,
        program_id: uuid_mod.UUID,
        entries: Sequence[Dict[str, Any]],
    ) -> int:
        """Promote target_key rows to asset_id rows; returns count of target rows removed."""
        key_to_assets: Dict[str, List[Tuple[str, uuid_mod.UUID]]] = {}
        for entry in entries:
            asset_type = entry.get("asset_type")
            asset_id = entry.get("asset_id")
            if not asset_type or not asset_id:
                continue
            try:
                normalized_type = normalize_asset_type(str(asset_type))
                aid = (
                    asset_id
                    if isinstance(asset_id, uuid_mod.UUID)
                    else uuid_mod.UUID(str(asset_id))
                )
            except (ValueError, TypeError):
                continue
            for target_key in entry.get("target_keys") or []:
                if not target_key:
                    continue
                key_to_assets.setdefault(str(target_key), []).append((normalized_type, aid))

        promoted_rows = 0
        for target_key, asset_targets in key_to_assets.items():
            unique_targets = list({(t, a) for t, a in asset_targets})
            rows = (
                db.query(TaskLastExecution)
                .filter(
                    TaskLastExecution.program_id == program_id,
                    TaskLastExecution.target_key == target_key,
                    TaskLastExecution.asset_id.is_(None),
                )
                .all()
            )
            if not rows:
                continue
            for row in rows:
                for atype, aid in unique_targets:
                    TaskLastExecutionsRepository.upsert_success_sync(
                        db,
                        program_id=program_id,
                        task_type=row.task_type,
                        asset_type=atype,
                        asset_id=aid,
                        params_fingerprint=row.params_fingerprint,
                        last_success_at=row.last_success_at,
                    )
                db.delete(row)
                promoted_rows += 1
        return promoted_rows

    @staticmethod
    def promote_target_keys_sync(
        db: Session,
        program_id: uuid_mod.UUID,
        *,
        asset_type: str,
        asset_id: uuid_mod.UUID,
        target_keys: Sequence[str],
    ) -> int:
        return TaskLastExecutionsRepository.promote_target_keys_batch_sync(
            db,
            program_id,
            [
                {
                    "asset_type": asset_type,
                    "asset_id": asset_id,
                    "target_keys": list(target_keys),
                }
            ],
        )

    @staticmethod
    async def promote_target_keys_batch(
        program_id: str,
        entries: Sequence[Dict[str, Any]],
    ) -> int:
        if not entries:
            return 0
        try:
            pid = uuid_mod.UUID(str(program_id))
        except ValueError:
            logger.warning("promote_target_keys_batch: invalid program_id %r", program_id)
            return 0
        try:
            async with get_db_session() as db:
                count = TaskLastExecutionsRepository.promote_target_keys_batch_sync(
                    db, pid, entries
                )
                db.commit()
                if count:
                    logger.info(
                        "Promoted %d task_last_executions target_key row(s) for program %s",
                        count,
                        program_id,
                    )
                return count
        except Exception as exc:
            logger.warning(
                "task_last_executions target_key promotion failed: %s",
                exc,
                exc_info=True,
            )
            return 0

    @staticmethod
    def _recent_asset_ids_subquery(
        program_id: uuid_mod.UUID,
        task_type: str,
        asset_type: str,
        fingerprint: str,
        cutoff: datetime,
    ):
        return (
            select(TaskLastExecution.asset_id)
            .where(
                TaskLastExecution.program_id == program_id,
                TaskLastExecution.task_type == task_type,
                TaskLastExecution.asset_type == asset_type,
                TaskLastExecution.params_fingerprint == fingerprint,
                TaskLastExecution.last_success_at >= cutoff,
            )
            .scalar_subquery()
        )

    @staticmethod
    async def search_eligible_assets(
        *,
        asset_type: str,
        program_id: uuid_mod.UUID,
        task_type: str,
        params: Optional[Dict[str, Any]],
        threshold_hours: int,
        limit: int,
        skip: int = 0,
        filter_type: Optional[str] = None,
        sort_by: str = "updated_at",
        sort_dir: str = "desc",
    ) -> Dict[str, Any]:
        normalized = normalize_asset_type(asset_type)
        fp = params_fingerprint(task_type, params)
        cutoff = utcnow() - timedelta(hours=threshold_hours)

        if normalized == "subdomain":
            return await TaskLastExecutionsRepository._search_eligible_subdomains(
                program_id=program_id,
                task_type=task_type,
                fingerprint=fp,
                cutoff=cutoff,
                limit=limit,
                skip=skip,
                filter_type=filter_type,
                sort_by=sort_by,
                sort_dir=sort_dir,
            )
        if normalized == "ip":
            return await TaskLastExecutionsRepository._search_eligible_ips(
                program_id=program_id,
                task_type=task_type,
                fingerprint=fp,
                cutoff=cutoff,
                limit=limit,
                skip=skip,
                filter_type=filter_type,
                sort_by=sort_by,
                sort_dir=sort_dir,
            )
        if normalized == "url":
            return await TaskLastExecutionsRepository._search_eligible_urls(
                program_id=program_id,
                task_type=task_type,
                fingerprint=fp,
                cutoff=cutoff,
                limit=limit,
                skip=skip,
                filter_type=filter_type,
                sort_by=sort_by,
                sort_dir=sort_dir,
            )
        if normalized == "apex_domain":
            return await TaskLastExecutionsRepository._search_eligible_apex_domains(
                program_id=program_id,
                task_type=task_type,
                fingerprint=fp,
                cutoff=cutoff,
                limit=limit,
                skip=skip,
                sort_by=sort_by,
                sort_dir=sort_dir,
            )
        if normalized == "service":
            return await TaskLastExecutionsRepository._search_eligible_simple(
                program_id=program_id,
                task_type=task_type,
                asset_type="service",
                model=Service,
                fingerprint=fp,
                cutoff=cutoff,
                limit=limit,
                skip=skip,
                sort_by=sort_by,
                sort_dir=sort_dir,
                item_builder=lambda r: {
                    "id": str(r.id),
                    "updated_at": r.updated_at.isoformat() if r.updated_at else None,
                },
            )
        if normalized == "certificate":
            return await TaskLastExecutionsRepository._search_eligible_simple(
                program_id=program_id,
                task_type=task_type,
                asset_type="certificate",
                model=Certificate,
                fingerprint=fp,
                cutoff=cutoff,
                limit=limit,
                skip=skip,
                sort_by=sort_by,
                sort_dir=sort_dir,
                item_builder=lambda r: {
                    "id": str(r.id),
                    "updated_at": r.updated_at.isoformat() if r.updated_at else None,
                },
            )
        raise ValueError(f"Unsupported asset type: {asset_type}")

    @staticmethod
    async def _search_eligible_subdomains(
        *,
        program_id: uuid_mod.UUID,
        task_type: str,
        fingerprint: str,
        cutoff: datetime,
        limit: int,
        skip: int,
        filter_type: Optional[str],
        sort_by: str,
        sort_dir: str,
    ) -> Dict[str, Any]:
        async with get_db_session() as db:
            recent_ids = TaskLastExecutionsRepository._recent_asset_ids_subquery(
                program_id, task_type, "subdomain", fingerprint, cutoff
            )
            count_ip_col = func.count(func.distinct(IP.id))
            ip_array_col = func.array_remove(
                func.array_agg(func.distinct(func.host(IP.ip_address))),
                None,
            )
            base = (
                db.query(
                    Subdomain.id,
                    Subdomain.name,
                    Subdomain.is_wildcard,
                    Subdomain.cname_record,
                    Subdomain.created_at,
                    Subdomain.updated_at,
                    ip_array_col.label("ip"),
                    count_ip_col.label("ip_count"),
                )
                .outerjoin(SubdomainIP, Subdomain.id == SubdomainIP.subdomain_id)
                .outerjoin(IP, IP.id == SubdomainIP.ip_id)
                .filter(Subdomain.program_id == program_id)
                .filter(~Subdomain.id.in_(recent_ids))
            )
            if filter_type == "resolved":
                base = base.having(func.count(func.distinct(IP.id)) > 0)
            elif filter_type == "unresolved":
                base = base.having(func.count(func.distinct(IP.id)) == 0)

            base = base.group_by(
                Subdomain.id,
                Subdomain.name,
                Subdomain.is_wildcard,
                Subdomain.cname_record,
                Subdomain.created_at,
                Subdomain.updated_at,
            )

            count_subq = base.subquery()
            total_count = db.query(func.count()).select_from(count_subq).scalar() or 0

            direction = asc if sort_dir == "asc" else desc
            sort_col = getattr(Subdomain, sort_by, Subdomain.updated_at)
            rows = base.order_by(direction(sort_col)).offset(skip).limit(limit).all()

            items = [
                {
                    "id": str(r.id),
                    "name": r.name,
                    "is_wildcard": r.is_wildcard,
                    "cname_record": r.cname_record,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "updated_at": r.updated_at.isoformat() if r.updated_at else None,
                    "ip": list(r.ip) if r.ip else [],
                    "ip_count": int(r.ip_count or 0),
                }
                for r in rows
            ]
            return {"items": items, "total_count": int(total_count)}

    @staticmethod
    async def _search_eligible_ips(
        *,
        program_id: uuid_mod.UUID,
        task_type: str,
        fingerprint: str,
        cutoff: datetime,
        limit: int,
        skip: int,
        filter_type: Optional[str],
        sort_by: str,
        sort_dir: str,
    ) -> Dict[str, Any]:
        async with get_db_session() as db:
            recent_ids = TaskLastExecutionsRepository._recent_asset_ids_subquery(
                program_id, task_type, "ip", fingerprint, cutoff
            )
            base = db.query(IP).filter(
                IP.program_id == program_id,
                ~IP.id.in_(recent_ids),
            )
            if filter_type == "resolved":
                base = base.filter(and_(IP.ptr_record.isnot(None), IP.ptr_record != ""))
            elif filter_type == "unresolved":
                base = base.filter(or_(IP.ptr_record.is_(None), IP.ptr_record == ""))

            total_count = base.count()
            direction = asc if sort_dir == "asc" else desc
            if sort_by == "ip_address":
                sort_col = IP.ip_address
            else:
                sort_col = getattr(IP, sort_by, IP.updated_at)
            rows = base.order_by(direction(sort_col)).offset(skip).limit(limit).all()
            items = [
                {
                    "id": str(r.id),
                    "ip_address": str(r.ip_address),
                    "ptr_record": r.ptr_record,
                    "service_provider": r.service_provider,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "updated_at": r.updated_at.isoformat() if r.updated_at else None,
                }
                for r in rows
            ]
            return {"items": items, "total_count": int(total_count)}

    @staticmethod
    async def _search_eligible_urls(
        *,
        program_id: uuid_mod.UUID,
        task_type: str,
        fingerprint: str,
        cutoff: datetime,
        limit: int,
        skip: int,
        filter_type: Optional[str],
        sort_by: str,
        sort_dir: str,
    ) -> Dict[str, Any]:
        async with get_db_session() as db:
            recent_ids = TaskLastExecutionsRepository._recent_asset_ids_subquery(
                program_id, task_type, "url", fingerprint, cutoff
            )
            base = db.query(URL).filter(
                URL.program_id == program_id,
                ~URL.id.in_(recent_ids),
            )
            if filter_type == "root":
                base = base.filter(URL.path == "/")

            total_count = base.count()
            direction = asc if sort_dir == "asc" else desc
            sort_col = getattr(URL, sort_by, URL.updated_at)
            rows = base.order_by(direction(sort_col)).offset(skip).limit(limit).all()
            items = [
                {
                    "id": str(r.id),
                    "url": r.url,
                    "path": r.path,
                    "hostname": r.hostname,
                    "port": r.port,
                    "scheme": r.scheme,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "updated_at": r.updated_at.isoformat() if r.updated_at else None,
                }
                for r in rows
            ]
            return {"items": items, "total_count": int(total_count)}

    @staticmethod
    async def _search_eligible_apex_domains(
        *,
        program_id: uuid_mod.UUID,
        task_type: str,
        fingerprint: str,
        cutoff: datetime,
        limit: int,
        skip: int,
        sort_by: str,
        sort_dir: str,
    ) -> Dict[str, Any]:
        async with get_db_session() as db:
            recent_ids = TaskLastExecutionsRepository._recent_asset_ids_subquery(
                program_id, task_type, "apex_domain", fingerprint, cutoff
            )
            base = db.query(ApexDomain).filter(
                ApexDomain.program_id == program_id,
                ~ApexDomain.id.in_(recent_ids),
            )
            total_count = base.count()
            direction = asc if sort_dir == "asc" else desc
            sort_col = getattr(ApexDomain, sort_by, ApexDomain.updated_at)
            rows = base.order_by(direction(sort_col)).offset(skip).limit(limit).all()
            items = [
                {
                    "id": str(r.id),
                    "name": r.name,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "updated_at": r.updated_at.isoformat() if r.updated_at else None,
                }
                for r in rows
            ]
            return {"items": items, "total_count": int(total_count)}

    @staticmethod
    async def _search_eligible_simple(
        *,
        program_id: uuid_mod.UUID,
        task_type: str,
        asset_type: str,
        model,
        fingerprint: str,
        cutoff: datetime,
        limit: int,
        skip: int,
        sort_by: str,
        sort_dir: str,
        item_builder,
    ) -> Dict[str, Any]:
        async with get_db_session() as db:
            recent_ids = TaskLastExecutionsRepository._recent_asset_ids_subquery(
                program_id, task_type, asset_type, fingerprint, cutoff
            )
            base = db.query(model).filter(
                model.program_id == program_id,
                ~model.id.in_(recent_ids),
            )
            total_count = base.count()
            direction = asc if sort_dir == "asc" else desc
            sort_col = getattr(model, sort_by, model.updated_at)
            rows = base.order_by(direction(sort_col)).offset(skip).limit(limit).all()
            return {"items": [item_builder(r) for r in rows], "total_count": int(total_count)}

    @staticmethod
    async def filter_recent_targets(
        *,
        program_id: uuid_mod.UUID,
        task_type: str,
        params: Optional[Dict[str, Any]],
        threshold_hours: int,
        targets: Sequence[str],
    ) -> List[str]:
        if not targets:
            return []
        fp = params_fingerprint(task_type, params)
        cutoff = utcnow() - timedelta(hours=threshold_hours)

        async with get_db_session() as db:
            target_to_pairs: Dict[str, List[Tuple[str, uuid_mod.UUID]]] = {}
            target_to_key: Dict[str, str] = {}
            all_pairs: Set[Tuple[str, uuid_mod.UUID]] = set()
            all_target_keys: Set[str] = set()
            for raw in targets:
                if not raw or not isinstance(raw, str):
                    continue
                stripped = raw.strip()
                if not stripped:
                    continue
                pairs = resolve_target_strings_to_asset_pairs(db, program_id, [stripped])
                if pairs:
                    target_to_pairs[raw] = pairs
                    all_pairs.update(pairs)
                key = normalize_target_key(stripped)
                if key:
                    target_to_key[raw] = key
                    all_target_keys.add(key)

            if not all_pairs and not all_target_keys:
                return []

            recent_pairs: Set[Tuple[str, uuid_mod.UUID]] = set()
            if all_pairs:
                by_type: Dict[str, List[uuid_mod.UUID]] = {}
                for atype, aid in all_pairs:
                    by_type.setdefault(atype, []).append(aid)

                for atype, aids in by_type.items():
                    rows = (
                        db.query(TaskLastExecution.asset_id)
                        .filter(
                            TaskLastExecution.program_id == program_id,
                            TaskLastExecution.task_type == task_type,
                            TaskLastExecution.asset_type == atype,
                            TaskLastExecution.params_fingerprint == fp,
                            TaskLastExecution.asset_id.in_(aids),
                            TaskLastExecution.last_success_at >= cutoff,
                        )
                        .all()
                    )
                    for (aid,) in rows:
                        recent_pairs.add((atype, aid))

            recent_target_keys: Set[str] = set()
            if all_target_keys:
                rows = (
                    db.query(TaskLastExecution.target_key)
                    .filter(
                        TaskLastExecution.program_id == program_id,
                        TaskLastExecution.task_type == task_type,
                        TaskLastExecution.params_fingerprint == fp,
                        TaskLastExecution.target_key.in_(list(all_target_keys)),
                        TaskLastExecution.last_success_at >= cutoff,
                    )
                    .all()
                )
                for (key,) in rows:
                    if key:
                        recent_target_keys.add(key)

            recent_targets: List[str] = []
            for raw in targets:
                if not raw or not isinstance(raw, str):
                    continue
                pairs = target_to_pairs.get(raw)
                if pairs and any(p in recent_pairs for p in pairs):
                    recent_targets.append(raw)
                    continue
                key = target_to_key.get(raw)
                if key and key in recent_target_keys:
                    recent_targets.append(raw)
            return recent_targets
