from utils.query_filters import ProgramAccessMixin
from typing import Dict, Any, List, Optional
from datetime import datetime, date, timedelta
from models.postgres import (
    AssetStatsResponse,
    AggregatedAssetStatsResponse,
    SubdomainStats,
    ApexDomainStats,
    IPStats,
    URLStats,
    ServiceStats,
    CertificateStats,
    AssetTrendBucket,
    AssetTrendsResponse,
)
from sqlalchemy import and_, or_, desc, func
from sqlalchemy.orm import joinedload
from models.postgres import Program, ApexDomain, Subdomain, IP, Service, URL, SubdomainIP, Certificate
from db import SessionLocal
from fastapi.concurrency import run_in_threadpool
from models.base import utcnow
import logging

logger = logging.getLogger(__name__)

class CommonAssetsRepository(ProgramAccessMixin):
    """PostgreSQL repository for assets operations"""

    @staticmethod
    def _compute_asset_stats(
        db,
        program_ids: List[Any],
        *,
        url_https_http_breakdown: bool,
    ):
        """Shared COUNT(*) FILTER aggregates for program_id IN program_ids."""
        now = utcnow()
        thirty_days_from_now = now + timedelta(days=30)
        root_path = or_(URL.path == "/", URL.path == "", URL.path.is_(None))

        apex = int(
            db.query(func.count(ApexDomain.id)).filter(ApexDomain.program_id.in_(program_ids)).scalar() or 0
        )

        srow = (
            db.query(
                func.count(Subdomain.id),
                func.count().filter(Subdomain.is_wildcard.is_(True)),
            )
            .filter(Subdomain.program_id.in_(program_ids))
            .one()
        )
        total_subdomains = int(srow[0] or 0)
        wildcard_subdomains = int(srow[1] or 0)
        resolved_subdomains = (
            db.query(func.count(func.distinct(Subdomain.id)))
            .select_from(Subdomain)
            .join(SubdomainIP, SubdomainIP.subdomain_id == Subdomain.id)
            .filter(Subdomain.program_id.in_(program_ids))
            .scalar()
        ) or 0

        irow = (
            db.query(
                func.count(IP.id),
                func.count().filter(and_(IP.ptr_record.isnot(None), IP.ptr_record != "")),
            )
            .filter(IP.program_id.in_(program_ids))
            .one()
        )
        total_ips = int(irow[0] or 0)
        resolved_ips = int(irow[1] or 0)

        if url_https_http_breakdown:
            urow = (
                db.query(
                    func.count(URL.id),
                    func.count().filter(root_path),
                    func.count().filter(and_(URL.scheme == "https", URL.path == "/")),
                    func.count().filter(and_(URL.scheme == "http", URL.path == "/")),
                )
                .filter(URL.program_id.in_(program_ids))
                .one()
            )
            total_urls = int(urow[0] or 0)
            root_urls = int(urow[1] or 0)
            root_urls_https = int(urow[2] or 0)
            root_urls_http = int(urow[3] or 0)
        else:
            urow = (
                db.query(
                    func.count(URL.id),
                    func.count().filter(root_path),
                )
                .filter(URL.program_id.in_(program_ids))
                .one()
            )
            total_urls = int(urow[0] or 0)
            root_urls = int(urow[1] or 0)
            root_urls_https = 0
            root_urls_http = 0

        service_count = (
            db.query(func.count(Service.id)).filter(Service.program_id.in_(program_ids)).scalar() or 0
        )

        crow = (
            db.query(
                func.count(Certificate.id),
                func.count().filter(Certificate.valid_until > thirty_days_from_now),
                func.count().filter(
                    and_(
                        Certificate.valid_until <= thirty_days_from_now,
                        Certificate.valid_until > now,
                    )
                ),
                func.count().filter(Certificate.valid_until <= now),
                func.count().filter(
                    and_(
                        Certificate.issuer_dn == Certificate.subject_dn,
                        Certificate.issuer_dn.isnot(None),
                        Certificate.subject_dn.isnot(None),
                    )
                ),
                func.count().filter(
                    or_(
                        func.lower(Certificate.subject_dn).like("%*%"),
                        func.array_to_string(Certificate.subject_alternative_names, ",").like("%*%"),
                    )
                ),
            )
            .filter(Certificate.program_id.in_(program_ids))
            .one()
        )

        return dict(
            apex_domain_stats=ApexDomainStats(total=apex),
            subdomain_stats=SubdomainStats(
                total=total_subdomains,
                resolved=int(resolved_subdomains),
                unresolved=total_subdomains - int(resolved_subdomains),
                wildcard=wildcard_subdomains,
            ),
            ip_stats=IPStats(
                total=total_ips,
                resolved=resolved_ips,
                unresolved=total_ips - resolved_ips,
            ),
            url_stats=URLStats(
                total=total_urls,
                root=root_urls,
                non_root=total_urls - root_urls,
                root_https=root_urls_https,
                root_http=root_urls_http,
            ),
            service_stats=ServiceStats(total=int(service_count)),
            certificate_stats=CertificateStats(
                total=int(crow[0] or 0),
                valid=int(crow[1] or 0),
                expiring_soon=int(crow[2] or 0),
                expired=int(crow[3] or 0),
                self_signed=int(crow[4] or 0),
                wildcards=int(crow[5] or 0),
            ),
        )

    @staticmethod
    def _get_detailed_asset_stats_sync(filter_data: Dict[str, Any]) -> AssetStatsResponse:
        program_name = filter_data.get("program_name")
        if not program_name:
            logger.warning("No program_name provided for asset stats")
            return AssetStatsResponse()

        db = SessionLocal()
        try:
            program = db.query(Program).filter(Program.name == program_name).first()
            if not program:
                logger.warning("Program %s not found", program_name)
                return AssetStatsResponse()

            bundle = CommonAssetsRepository._compute_asset_stats(
                db, [program.id], url_https_http_breakdown=True
            )
            return AssetStatsResponse(
                apex_domain_details=bundle["apex_domain_stats"],
                subdomain_details=bundle["subdomain_stats"],
                ip_details=bundle["ip_stats"],
                service_details=bundle["service_stats"],
                url_details=bundle["url_stats"],
                certificate_details=bundle["certificate_stats"],
            )
        except Exception as exc:
            logger.exception("Error calculating detailed asset stats for filter %s: %s", filter_data, exc)
            return AssetStatsResponse(
                apex_domain_details=ApexDomainStats(),
                subdomain_details=SubdomainStats(),
                ip_details=IPStats(),
                service_details=ServiceStats(),
                url_details=URLStats(),
            )
        finally:
            db.close()

    @staticmethod
    def _get_aggregated_asset_stats_sync(program_names: Optional[List[str]]) -> AggregatedAssetStatsResponse:
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
                logger.warning("No programs found for aggregated asset stats")
                return AggregatedAssetStatsResponse()

            bundle = CommonAssetsRepository._compute_asset_stats(
                db, program_ids, url_https_http_breakdown=False
            )
            return AggregatedAssetStatsResponse(
                total_programs=total_programs,
                apex_domain_details=bundle["apex_domain_stats"],
                subdomain_details=bundle["subdomain_stats"],
                ip_details=bundle["ip_stats"],
                service_details=bundle["service_stats"],
                url_details=bundle["url_stats"],
                certificate_details=bundle["certificate_stats"],
            )
        except Exception as exc:
            logger.exception("Error calculating aggregated asset stats: %s", exc)
            return AggregatedAssetStatsResponse(
                total_programs=0,
                apex_domain_details=ApexDomainStats(),
                subdomain_details=SubdomainStats(),
                ip_details=IPStats(),
                service_details=ServiceStats(),
                url_details=URLStats(),
            )
        finally:
            db.close()

    @staticmethod
    async def get_detailed_asset_stats(filter_data: Dict[str, Any]) -> AssetStatsResponse:
        """Get detailed asset stats for a program"""
        return await run_in_threadpool(CommonAssetsRepository._get_detailed_asset_stats_sync, filter_data)

    @staticmethod
    async def get_aggregated_asset_stats(program_names: Optional[List[str]] = None) -> AggregatedAssetStatsResponse:
        """Get aggregated asset stats across multiple programs"""
        return await run_in_threadpool(CommonAssetsRepository._get_aggregated_asset_stats_sync, program_names)

    _LATEST_ASSET_TYPE_KEYS = frozenset(
        {"apex_domains", "subdomains", "ips", "urls", "services", "certificates"}
    )

    @staticmethod
    def _normalize_latest_asset_types(asset_types: Optional[List[str]]) -> frozenset:
        if not asset_types:
            return CommonAssetsRepository._LATEST_ASSET_TYPE_KEYS
        out: set = set()
        for raw in asset_types:
            if raw is None or not str(raw).strip():
                continue
            k = str(raw).strip().lower()
            if k in CommonAssetsRepository._LATEST_ASSET_TYPE_KEYS:
                out.add(k)
            elif k == "subdomain":
                out.add("subdomains")
            elif k == "url":
                out.add("urls")
        return frozenset(out) if out else CommonAssetsRepository._LATEST_ASSET_TYPE_KEYS

    @staticmethod
    def _get_latest_assets_sync(
        program_name: Optional[str],
        limit: int,
        days_ago: Optional[int],
        asset_types: Optional[List[str]],
        restrict_to_program_names: Optional[List[str]] = None,
    ) -> Dict[str, List]:
        want = CommonAssetsRepository._normalize_latest_asset_types(asset_types)
        db = SessionLocal()
        latest_assets: Dict[str, List] = {}
        try:
            program_ids_filter: Optional[List] = None
            if program_name:
                program = db.query(Program).filter(Program.name == program_name).first()
                if not program:
                    logger.warning("Program %s not found for latest assets", program_name)
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

            def _apply_prog_time(q, model, pid_column):
                if program_ids_filter is not None:
                    q = q.filter(pid_column.in_(program_ids_filter))
                if time_filter is not None:
                    q = q.filter(model.created_at >= time_filter)
                return q

            if "apex_domains" in want:
                try:
                    q = db.query(ApexDomain).options(joinedload(ApexDomain.program))
                    q = _apply_prog_time(q, ApexDomain, ApexDomain.program_id)
                    latest_apex = q.order_by(desc(ApexDomain.created_at)).limit(limit).all()
                    latest_assets["apex_domains"] = [
                        {
                            "id": domain.id,
                            "name": domain.name,
                            "created_at": domain.created_at,
                            "program_name": domain.program.name if domain.program else None,
                        }
                        for domain in latest_apex
                    ]
                except Exception as exc:
                    logger.error("Error getting apex domains: %s", exc)
                    latest_assets["apex_domains"] = []

            if "subdomains" in want:
                try:
                    q = db.query(Subdomain).options(joinedload(Subdomain.program))
                    q = _apply_prog_time(q, Subdomain, Subdomain.program_id)
                    rows = q.order_by(desc(Subdomain.created_at)).limit(limit).all()
                    latest_assets["subdomains"] = [
                        {
                            "id": row.id,
                            "name": row.name,
                            "created_at": row.created_at,
                            "program_name": row.program.name if row.program else None,
                            "is_wildcard": row.is_wildcard,
                        }
                        for row in rows
                    ]
                except Exception as exc:
                    logger.error("Error getting subdomains: %s", exc)
                    latest_assets["subdomains"] = []

            if "ips" in want:
                try:
                    q = db.query(IP).options(joinedload(IP.program))
                    q = _apply_prog_time(q, IP, IP.program_id)
                    rows = q.order_by(desc(IP.created_at)).limit(limit).all()
                    latest_assets["ips"] = [
                        {
                            "id": row.id,
                            "ip": row.ip_address,
                            "created_at": row.created_at,
                            "program_name": row.program.name if row.program else None,
                            "ptr_record": row.ptr_record,
                        }
                        for row in rows
                    ]
                except Exception as exc:
                    logger.error("Error getting IPs: %s", exc)
                    latest_assets["ips"] = []

            if "urls" in want:
                try:
                    q = db.query(URL).options(joinedload(URL.program)).filter(URL.path == "/")
                    q = _apply_prog_time(q, URL, URL.program_id)
                    rows = q.order_by(desc(URL.created_at)).limit(limit).all()
                    latest_assets["urls"] = [
                        {
                            "id": row.id,
                            "url": row.url,
                            "created_at": row.created_at,
                            "program_name": row.program.name if row.program else None,
                            "status_code": row.http_status_code,
                            "scheme": row.scheme,
                            "hostname": row.hostname,
                        }
                        for row in rows
                    ]
                except Exception as exc:
                    logger.error("Error getting URLs: %s", exc)
                    latest_assets["urls"] = []

            if "services" in want:
                try:
                    q = db.query(Service).options(joinedload(Service.program), joinedload(Service.ip))
                    q = _apply_prog_time(q, Service, Service.program_id)
                    latest_services = q.order_by(desc(Service.created_at)).limit(limit).all()
                    processed_services = []
                    for service in latest_services:
                        ip_address = None
                        if service.ip:
                            ip_address = service.ip.ip_address
                        else:
                            ip_obj = db.query(IP).filter(IP.id == service.ip_id).first()
                            ip_address = ip_obj.ip_address if ip_obj else "N/A"
                        processed_services.append(
                            {
                                "id": service.id,
                                "ip": ip_address,
                                "port": service.port,
                                "protocol": service.protocol,
                                "service_name": service.service_name,
                                "created_at": service.created_at,
                                "program_name": service.program.name if service.program else None,
                            }
                        )
                    latest_assets["services"] = processed_services
                except Exception as exc:
                    logger.error("Error getting services: %s", exc)
                    latest_assets["services"] = []

            if "certificates" in want:
                try:
                    q = db.query(Certificate).options(joinedload(Certificate.program))
                    q = _apply_prog_time(q, Certificate, Certificate.program_id)
                    rows = q.order_by(desc(Certificate.created_at)).limit(limit).all()
                    latest_assets["certificates"] = [
                        {
                            "id": cert.id,
                            "subject_dn": cert.subject_dn,
                            "issuer_dn": cert.issuer_dn,
                            "valid_from": cert.valid_from,
                            "valid_until": cert.valid_until,
                            "created_at": cert.created_at,
                            "program_name": cert.program.name if cert.program else None,
                        }
                        for cert in rows
                    ]
                except Exception as exc:
                    logger.error("Error getting certificates: %s", exc)
                    latest_assets["certificates"] = []

            return latest_assets
        except Exception as exc:
            logger.exception("Error getting latest assets: %s", exc)
            return {}
        finally:
            db.close()

    @staticmethod
    async def get_latest_assets(
        program_name: Optional[str] = None,
        limit: int = 5,
        days_ago: Optional[int] = None,
        asset_types: Optional[List[str]] = None,
        restrict_to_program_names: Optional[List[str]] = None,
    ) -> Dict[str, List]:
        """Get the latest assets of each type for dashboard display."""
        return await run_in_threadpool(
            CommonAssetsRepository._get_latest_assets_sync,
            program_name,
            limit,
            days_ago,
            asset_types,
            restrict_to_program_names,
        )

    @staticmethod
    def _asset_trend_day_expr(created_at_column):
        """PostgreSQL UTC calendar day for naive-UTC timestamps."""
        return func.date(func.timezone('UTC', created_at_column))

    @staticmethod
    def _daily_counts_for_model(
        db,
        model,
        program_ids: List,
        start_ts: datetime,
        end_ts_excl: datetime,
    ) -> Dict[date, int]:
        if not program_ids:
            return {}
        day_expr = CommonAssetsRepository._asset_trend_day_expr(model.created_at)
        rows = (
            db.query(day_expr.label('d'), func.count().label('c'))
            .filter(model.program_id.in_(program_ids))
            .filter(model.created_at >= start_ts)
            .filter(model.created_at < end_ts_excl)
            .group_by(day_expr)
            .all()
        )
        out: Dict[date, int] = {}
        for r in rows:
            d_val = r.d
            if d_val is None:
                continue
            if isinstance(d_val, datetime):
                d_val = d_val.date()
            out[d_val] = int(r.c or 0)
        return out

    @staticmethod
    def _get_asset_trends_body_sync(
        program_names: Optional[List[str]],
        sd: date,
        ed: date,
        num_days: int,
        start_ts: datetime,
        end_ts_excl: datetime,
    ) -> AssetTrendsResponse:
        db = SessionLocal()
        try:
            if program_names:
                programs = db.query(Program).filter(Program.name.in_(program_names)).all()
                program_ids = [p.id for p in programs]
            else:
                programs = db.query(Program).all()
                program_ids = [p.id for p in programs]

            if not program_ids:
                buckets = [
                    AssetTrendBucket(
                        date=(sd + timedelta(days=i)).isoformat(),
                        subdomains=0,
                        apex_domains=0,
                        ips=0,
                        urls=0,
                        services=0,
                        certificates=0,
                    )
                    for i in range(num_days)
                ]
                return AssetTrendsResponse(
                    days=num_days,
                    buckets=buckets,
                    start_date=sd.isoformat(),
                    end_date=ed.isoformat(),
                )

            sub_c = CommonAssetsRepository._daily_counts_for_model(
                db, Subdomain, program_ids, start_ts, end_ts_excl
            )
            apex_c = CommonAssetsRepository._daily_counts_for_model(
                db, ApexDomain, program_ids, start_ts, end_ts_excl
            )
            ip_c = CommonAssetsRepository._daily_counts_for_model(db, IP, program_ids, start_ts, end_ts_excl)
            url_c = CommonAssetsRepository._daily_counts_for_model(db, URL, program_ids, start_ts, end_ts_excl)
            svc_c = CommonAssetsRepository._daily_counts_for_model(
                db, Service, program_ids, start_ts, end_ts_excl
            )
            cert_c = CommonAssetsRepository._daily_counts_for_model(
                db, Certificate, program_ids, start_ts, end_ts_excl
            )

            buckets: List[AssetTrendBucket] = []
            for i in range(num_days):
                d = sd + timedelta(days=i)
                buckets.append(
                    AssetTrendBucket(
                        date=d.isoformat(),
                        subdomains=sub_c.get(d, 0),
                        apex_domains=apex_c.get(d, 0),
                        ips=ip_c.get(d, 0),
                        urls=url_c.get(d, 0),
                        services=svc_c.get(d, 0),
                        certificates=cert_c.get(d, 0),
                    )
                )

            return AssetTrendsResponse(
                days=num_days,
                buckets=buckets,
                start_date=sd.isoformat(),
                end_date=ed.isoformat(),
            )
        except Exception as exc:
            logger.exception("Error calculating asset trends: %s", exc)
            return AssetTrendsResponse(days=0, buckets=[], start_date=None, end_date=None)
        finally:
            db.close()

    @staticmethod
    async def get_asset_trends(
        *,
        program_names: Optional[List[str]] = None,
        start_day: Optional[date] = None,
        end_day: Optional[date] = None,
        days: int = 30,
    ) -> AssetTrendsResponse:
        """
        Daily created counts per asset type for accessible programs (UTC days).
        Either pass ``start_day`` and ``end_day`` (inclusive), or ``days`` ending today UTC.
        """
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
                CommonAssetsRepository._get_asset_trends_body_sync,
                program_names,
                sd,
                ed,
                num_days,
                start_ts,
                end_ts_excl,
            )
        except ValueError:
            raise
