import logging
import uuid
from datetime import timezone
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import asc, desc, func, or_

from db import get_db_session
from models.ct_monitor_log import CtMonitorLogIngestItem
from models.postgres import CtMonitorLog, Program
from models.base import utcnow

logger = logging.getLogger(__name__)


def _as_list(value: Any) -> Optional[List[str]]:
    if value is None:
        return None
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    text = str(value).strip()
    return [text] if text else None


def _dt_to_iso(value) -> Optional[str]:
    if value is None:
        return None
    if getattr(value, "tzinfo", None) is None:
        return value.isoformat() + "Z"
    return value.astimezone(timezone.utc).isoformat()


def _as_naive_utc(value):
    if value is None:
        return None
    if getattr(value, "tzinfo", None) is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _row_to_dict(row: CtMonitorLog, program_name: Optional[str] = None) -> Dict[str, Any]:
    return {
        "id": str(row.id),
        "program_id": str(row.program_id),
        "program_name": row.program_name or program_name or (row.program.name if row.program else None),
        "event_type": row.event_type,
        "outcome": row.outcome,
        "occurred_at": _dt_to_iso(row.occurred_at),
        "domain": row.domain,
        "protected_domain": row.protected_domain,
        "match_type": row.match_type,
        "similarity_score": row.similarity_score,
        "priority": row.priority,
        "cert_fingerprint": row.cert_fingerprint,
        "cert_issuer": row.cert_issuer,
        "cert_source": row.cert_source,
        "details": row.details or {},
        "created_at": _dt_to_iso(row.created_at),
    }


class CtMonitorLogsRepository:
    """PostgreSQL repository for durable CT monitor activity logs."""

    @staticmethod
    async def insert_logs(logs: Iterable[CtMonitorLogIngestItem]) -> Dict[str, Any]:
        items = list(logs)
        if not items:
            return {"inserted_count": 0, "error_count": 0, "errors": []}

        async with get_db_session() as db:
            program_ids: List[uuid.UUID] = []
            errors: List[str] = []
            for item in items:
                try:
                    program_ids.append(uuid.UUID(str(item.program_id)))
                except ValueError:
                    errors.append(f"Invalid program_id: {item.program_id}")

            if errors:
                return {"inserted_count": 0, "error_count": len(errors), "errors": errors}

            programs = {
                str(row.id): row.name
                for row in db.query(Program.id, Program.name).filter(Program.id.in_(program_ids)).all()
            }

            rows: List[CtMonitorLog] = []
            now = utcnow()
            for item in items:
                program_id = str(uuid.UUID(str(item.program_id)))
                if program_id not in programs:
                    errors.append(f"Program not found: {program_id}")
                    continue

                details = dict(item.details or {})
                if item.program_name and "program_name" not in details:
                    details["program_name"] = item.program_name

                rows.append(
                    CtMonitorLog(
                        program_id=uuid.UUID(program_id),
                        program_name=item.program_name or programs[program_id],
                        event_type=item.event_type,
                        outcome=item.outcome,
                        occurred_at=_as_naive_utc(item.occurred_at) or now,
                        domain=item.domain,
                        protected_domain=item.protected_domain,
                        match_type=item.match_type,
                        similarity_score=item.similarity_score,
                        priority=item.priority,
                        cert_fingerprint=item.cert_fingerprint,
                        cert_issuer=item.cert_issuer,
                        cert_source=item.cert_source,
                        details=details,
                    )
                )

            if rows:
                db.add_all(rows)
                db.commit()

            return {
                "inserted_count": len(rows),
                "error_count": len(errors),
                "errors": errors[:20],
            }

    @staticmethod
    async def search_logs_typed(
        *,
        programs: Optional[List[str]] = None,
        event_type: Any = None,
        outcome: Any = None,
        search: Optional[str] = None,
        match_type: Optional[str] = None,
        priority: Optional[str] = None,
        start_time=None,
        end_time=None,
        sort_by: str = "occurred_at",
        sort_dir: str = "desc",
        limit: int = 25,
        skip: int = 0,
    ) -> Dict[str, Any]:
        async with get_db_session() as db:
            base = db.query(CtMonitorLog, Program.name.label("program_name")).join(
                Program, Program.id == CtMonitorLog.program_id
            )

            if programs is not None:
                if not programs:
                    return {"items": [], "total_count": 0}
                base = base.filter(Program.name.in_(programs))

            event_types = _as_list(event_type)
            if event_types:
                base = base.filter(CtMonitorLog.event_type.in_(event_types))

            outcomes = _as_list(outcome)
            if outcomes:
                base = base.filter(CtMonitorLog.outcome.in_(outcomes))

            if match_type:
                base = base.filter(CtMonitorLog.match_type == match_type)

            if priority:
                base = base.filter(CtMonitorLog.priority == priority)

            if start_time is not None:
                base = base.filter(CtMonitorLog.occurred_at >= start_time)

            if end_time is not None:
                base = base.filter(CtMonitorLog.occurred_at <= end_time)

            if search:
                term = f"%{search.strip()}%"
                base = base.filter(
                    or_(
                        CtMonitorLog.domain.ilike(term),
                        CtMonitorLog.protected_domain.ilike(term),
                        CtMonitorLog.cert_fingerprint.ilike(term),
                        CtMonitorLog.cert_issuer.ilike(term),
                    )
                )

            count_query = base.with_entities(func.count(CtMonitorLog.id))
            total_count = int(count_query.scalar() or 0)

            sort_map = {
                "occurred_at": CtMonitorLog.occurred_at,
                "created_at": CtMonitorLog.created_at,
                "program_name": Program.name,
                "event_type": CtMonitorLog.event_type,
                "outcome": CtMonitorLog.outcome,
                "domain": CtMonitorLog.domain,
                "similarity_score": CtMonitorLog.similarity_score,
            }
            sort_col = sort_map.get(sort_by, CtMonitorLog.occurred_at)
            direction = asc if sort_dir == "asc" else desc
            rows = base.order_by(direction(sort_col), desc(CtMonitorLog.created_at)).offset(skip).limit(limit).all()

            return {
                "items": [_row_to_dict(row, program_name) for row, program_name in rows],
                "total_count": total_count,
            }
