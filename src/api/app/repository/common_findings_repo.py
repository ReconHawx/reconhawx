from utils.query_filters import ProgramAccessMixin
from typing import Dict, Any, List, Optional

from models.base import utcnow
from models.postgres import (
    FindingsStatsResponse,
    AggregatedFindingsStatsResponse,
    NucleiFindingStats,
    TyposquatFindingStats,
    FindingsTrendBucket,
    FindingsTrendsResponse,
)
from sqlalchemy import desc, func, case
from models.postgres import Program, NucleiFinding, TyposquatDomain
from db import SessionLocal
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import joinedload
import logging
from datetime import datetime, date, timedelta

logger = logging.getLogger(__name__)


class CommonFindingsRepository(ProgramAccessMixin):
    """PostgreSQL repository for findings operations"""

    _FINDING_KEYS = frozenset({"nuclei", "typosquat"})

    @staticmethod
    def _normalize_finding_types(finding_types: Optional[List[str]]) -> frozenset:
        if not finding_types:
            return CommonFindingsRepository._FINDING_KEYS
        out = set()
        for raw in finding_types:
            if raw is None or not str(raw).strip():
                continue
            k = str(raw).strip().lower()
            if k in CommonFindingsRepository._FINDING_KEYS:
                out.add(k)
        return frozenset(out) if out else CommonFindingsRepository._FINDING_KEYS

    @staticmethod
    def _compute_findings_stats_bundle(db, program_ids: List[Any]):
        nrow = (
            db.query(
                func.count(NucleiFinding.id),
                func.count().filter(NucleiFinding.severity == "critical"),
                func.count().filter(NucleiFinding.severity == "high"),
                func.count().filter(NucleiFinding.severity == "medium"),
                func.count().filter(NucleiFinding.severity == "low"),
                func.count().filter(NucleiFinding.severity == "info"),
            )
            .filter(NucleiFinding.program_id.in_(program_ids))
            .one()
        )

        trow = (
            db.query(
                func.count(TyposquatDomain.id),
                func.count().filter(TyposquatDomain.status == "new"),
                func.count().filter(TyposquatDomain.status == "investigating"),
                func.count().filter(TyposquatDomain.status == "resolved"),
                func.count().filter(TyposquatDomain.status == "dismissed"),
            )
            .filter(TyposquatDomain.program_id.in_(program_ids))
            .one()
        )

        return dict(
            nuclei_stats=NucleiFindingStats(
                total=int(nrow[0] or 0),
                critical=int(nrow[1] or 0),
                high=int(nrow[2] or 0),
                medium=int(nrow[3] or 0),
                low=int(nrow[4] or 0),
                info=int(nrow[5] or 0),
            ),
            typosquat_stats=TyposquatFindingStats(
                total=int(trow[0] or 0),
                new=int(trow[1] or 0),
                inprogress=int(trow[2] or 0),
                resolved=int(trow[3] or 0),
                dismissed=int(trow[4] or 0),
            ),
        )

    @staticmethod
    def _get_detailed_findings_stats_sync(filter_data: Dict[str, Any]) -> FindingsStatsResponse:
        program_name = filter_data.get("program_name")
        if not program_name:
            logger.warning("No program_name provided for findings stats")
            return FindingsStatsResponse()

        db = SessionLocal()
        try:
            program = db.query(Program).filter(Program.name == program_name).first()
            if not program:
                logger.warning("Program %s not found", program_name)
                return FindingsStatsResponse()

            bundle = CommonFindingsRepository._compute_findings_stats_bundle(db, [program.id])
            return FindingsStatsResponse(
                nuclei_findings=bundle["nuclei_stats"],
                typosquat_findings=bundle["typosquat_stats"],
            )
        except Exception as exc:
            logger.exception("Error calculating detailed findings stats for filter %s: %s", filter_data, exc)
            return FindingsStatsResponse(
                nuclei_findings=NucleiFindingStats(),
                typosquat_findings=TyposquatFindingStats(),
            )
        finally:
            db.close()

    @staticmethod
    def _get_aggregated_findings_stats_sync(program_names: Optional[List[str]]) -> AggregatedFindingsStatsResponse:
        db = SessionLocal()
        try:
            if program_names:
                programs = db.query(Program).filter(Program.name.in_(program_names)).all()
                program_ids = [p.id for p in programs]
                total_programs = len(programs)
            else:
                programs = db.query(Program).all()
                program_ids = [p.id for p in programs]
                total_programs = len(programs)

            if not program_ids:
                logger.warning("No programs found for aggregated findings stats")
                return AggregatedFindingsStatsResponse()

            bundle = CommonFindingsRepository._compute_findings_stats_bundle(db, program_ids)
            return AggregatedFindingsStatsResponse(
                total_programs=total_programs,
                nuclei_findings=bundle["nuclei_stats"],
                typosquat_findings=bundle["typosquat_stats"],
            )
        except Exception as exc:
            logger.exception("Error calculating aggregated findings stats: %s", exc)
            return AggregatedFindingsStatsResponse(
                total_programs=0,
                nuclei_findings=NucleiFindingStats(),
                typosquat_findings=TyposquatFindingStats(),
            )
        finally:
            db.close()

    @staticmethod
    async def get_detailed_findings_stats(filter_data: Dict[str, Any]) -> FindingsStatsResponse:
        """Get detailed findings stats for a program"""
        return await run_in_threadpool(CommonFindingsRepository._get_detailed_findings_stats_sync, filter_data)

    @staticmethod
    async def get_aggregated_findings_stats(
        program_names: Optional[List[str]] = None,
    ) -> AggregatedFindingsStatsResponse:
        """Get aggregated findings stats across multiple programs"""
        return await run_in_threadpool(CommonFindingsRepository._get_aggregated_findings_stats_sync, program_names)

    @staticmethod
    def _get_latest_findings_sync(
        program_name: Optional[str],
        limit: int,
        days_ago: Optional[int],
        finding_types: Optional[List[str]],
        restrict_to_program_names: Optional[List[str]] = None,
    ) -> Dict[str, List]:
        want = CommonFindingsRepository._normalize_finding_types(finding_types)
        db = SessionLocal()
        out: Dict[str, List] = {}
        try:
            program_ids_filter: Optional[List] = None
            if program_name:
                program = db.query(Program).filter(Program.name == program_name).first()
                if not program:
                    logger.warning("Program %s not found for latest findings", program_name)
                    return {}
                program_ids_filter = [program.id]
            elif restrict_to_program_names is not None:
                if len(restrict_to_program_names) == 0:
                    return {}
                programs = db.query(Program).filter(Program.name.in_(restrict_to_program_names)).all()
                program_ids_filter = [p.id for p in programs]
                if not program_ids_filter:
                    return {}

            time_filter = None
            if days_ago:
                time_filter = utcnow() - timedelta(days=days_ago)

            if "nuclei" in want:
                try:
                    q = db.query(NucleiFinding).options(joinedload(NucleiFinding.program))
                    if program_ids_filter:
                        q = q.filter(NucleiFinding.program_id.in_(program_ids_filter))
                    if time_filter:
                        q = q.filter(NucleiFinding.created_at >= time_filter)
                    rows = q.order_by(desc(NucleiFinding.created_at)).limit(limit).all()
                    out["nuclei"] = [
                        {
                            "id": f.id,
                            "name": f.name,
                            "severity": f.severity,
                            "url": f.url,
                            "template_id": f.template_id,
                            "created_at": f.created_at,
                            "program_name": f.program.name if f.program else None,
                            "status": getattr(f, "status", "unknown"),
                            "hostname": getattr(f, "hostname", None),
                            "type": getattr(f, "finding_type", None),
                        }
                        for f in rows
                    ]
                except Exception as exc:
                    logger.error("Error getting nuclei findings: %s", exc)
                    out["nuclei"] = []

            if "typosquat" in want:
                try:
                    q = db.query(TyposquatDomain).options(joinedload(TyposquatDomain.program))
                    if program_ids_filter:
                        q = q.filter(TyposquatDomain.program_id.in_(program_ids_filter))
                    if time_filter:
                        q = q.filter(TyposquatDomain.created_at >= time_filter)
                    rows = q.order_by(desc(TyposquatDomain.created_at)).limit(limit).all()
                    out["typosquat"] = [
                        {
                            "id": finding.id,
                            "typo_domain": finding.typo_domain,
                            "status": finding.status,
                            "risk_score": finding.risk_score,
                            "created_at": finding.created_at,
                            "program_name": finding.program.name if finding.program else None,
                        }
                        for finding in rows
                    ]
                except Exception as exc:
                    logger.error("Error getting typosquat findings: %s", exc)
                    out["typosquat"] = []

            return out
        except Exception as exc:
            logger.exception("Error getting latest findings: %s", exc)
            return {}
        finally:
            db.close()

    @staticmethod
    async def get_latest_findings(
        program_name: Optional[str] = None,
        limit: int = 5,
        days_ago: Optional[int] = None,
        finding_types: Optional[List[str]] = None,
        restrict_to_program_names: Optional[List[str]] = None,
    ) -> Dict[str, List]:
        """Get the latest findings of each type for dashboard display"""
        return await run_in_threadpool(
            CommonFindingsRepository._get_latest_findings_sync,
            program_name,
            limit,
            days_ago,
            finding_types,
            restrict_to_program_names,
        )

    @staticmethod
    def _findings_trend_day_expr(created_at_column):
        return func.date(func.timezone("UTC", created_at_column))

    @staticmethod
    def _get_findings_trends_body_sync(
        program_names: Optional[List[str]],
        sd: date,
        ed: date,
        num_days: int,
        start_ts: datetime,
        end_ts_excl: datetime,
    ) -> FindingsTrendsResponse:
        db = SessionLocal()
        try:
            if program_names:
                programs = db.query(Program).filter(Program.name.in_(program_names)).all()
                program_ids = [p.id for p in programs]
            else:
                programs = db.query(Program).all()
                program_ids = [p.id for p in programs]

            nuclei_by_day: Dict[date, Dict[str, int]] = {}
            typo_by_day: Dict[date, Dict[str, int]] = {}

            if program_ids:
                nd = CommonFindingsRepository._findings_trend_day_expr(NucleiFinding.created_at)
                nrows = (
                    db.query(
                        nd.label("d"),
                        func.count().label("total"),
                        func.coalesce(
                            func.sum(case((NucleiFinding.severity == "critical", 1), else_=0)),
                            0,
                        ).label("crit"),
                        func.coalesce(
                            func.sum(case((NucleiFinding.severity == "high", 1), else_=0)),
                            0,
                        ).label("high"),
                    )
                    .filter(NucleiFinding.program_id.in_(program_ids))
                    .filter(NucleiFinding.created_at >= start_ts)
                    .filter(NucleiFinding.created_at < end_ts_excl)
                    .group_by(nd)
                    .all()
                )
                for r in nrows:
                    dv = r.d
                    if dv is None:
                        continue
                    if isinstance(dv, datetime):
                        dv = dv.date()
                    nuclei_by_day[dv] = {
                        "total": int(r.total or 0),
                        "critical": int(r.crit or 0),
                        "high": int(r.high or 0),
                    }

                td = CommonFindingsRepository._findings_trend_day_expr(TyposquatDomain.created_at)
                trows = (
                    db.query(
                        td.label("d"),
                        func.count().label("total"),
                        func.coalesce(
                            func.sum(case((TyposquatDomain.status == "new", 1), else_=0)),
                            0,
                        ).label("newn"),
                    )
                    .filter(TyposquatDomain.program_id.in_(program_ids))
                    .filter(TyposquatDomain.created_at >= start_ts)
                    .filter(TyposquatDomain.created_at < end_ts_excl)
                    .group_by(td)
                    .all()
                )
                for r in trows:
                    dv = r.d
                    if dv is None:
                        continue
                    if isinstance(dv, datetime):
                        dv = dv.date()
                    typo_by_day[dv] = {"total": int(r.total or 0), "new": int(r.newn or 0)}

            buckets: List[FindingsTrendBucket] = []
            for i in range(num_days):
                dday = sd + timedelta(days=i)
                n = nuclei_by_day.get(dday, {})
                t = typo_by_day.get(dday, {})
                buckets.append(
                    FindingsTrendBucket(
                        date=dday.isoformat(),
                        nuclei_total=n.get("total", 0),
                        nuclei_critical=n.get("critical", 0),
                        nuclei_high=n.get("high", 0),
                        typosquat_total=t.get("total", 0),
                        typosquat_new=t.get("new", 0),
                    )
                )

            return FindingsTrendsResponse(
                days=num_days,
                buckets=buckets,
                start_date=sd.isoformat(),
                end_date=ed.isoformat(),
            )
        except Exception as exc:
            logger.exception("Error calculating findings trends: %s", exc)
            return FindingsTrendsResponse(days=0, buckets=[], start_date=None, end_date=None)
        finally:
            db.close()

    @staticmethod
    async def get_findings_trends(
        *,
        program_names: Optional[List[str]] = None,
        start_day: Optional[date] = None,
        end_day: Optional[date] = None,
        days: int = 30,
    ) -> FindingsTrendsResponse:
        """Daily new-finding counts (UTC days) for Nuclei and Typosquat."""
        try:
            now = utcnow()
            if start_day is not None and end_day is not None:
                sd, ed = start_day, end_day
            else:
                ed = now.date()
                sd = ed - timedelta(days=max(1, min(int(days), 366)) - 1)

            if sd > ed:
                raise ValueError("start_date must be on or before end_date")
            if (ed - sd).days > 366:
                raise ValueError("Date range cannot exceed 366 days")

            num_days = (ed - sd).days + 1
            start_ts = datetime.combine(sd, datetime.min.time())
            end_ts_excl = datetime.combine(ed + timedelta(days=1), datetime.min.time())

            return await run_in_threadpool(
                CommonFindingsRepository._get_findings_trends_body_sync,
                program_names,
                sd,
                ed,
                num_days,
                start_ts,
                end_ts_excl,
            )
        except ValueError:
            raise
