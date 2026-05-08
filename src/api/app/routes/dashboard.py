"""Dashboard aggregate API for first-paint performance."""

import asyncio
import logging
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool

from auth.dependencies import (
    filter_by_user_programs,
    get_current_user_from_middleware,
    get_user_accessible_programs,
)
from models.user_postgres import UserResponse
from repository import (
    CommonAssetsRepository,
    CommonFindingsRepository,
    WorkflowRepository,
)
from repository.program_repo import ProgramRepository
from repository.url_assets_repo import UrlAssetsRepository
from routes.workflows import k8s_service, transform_workflow_executions_for_status_list

logger = logging.getLogger(__name__)
router = APIRouter()

_EMPTY_TREND_PROGRAM_SCOPE = "__reconhawx__empty_trend_scope__"


def _parse_iso_date_optional(value: Optional[str], field: str) -> Optional[date]:
    if value is None or value == "":
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid {field}; use YYYY-MM-DD") from exc


async def _resolve_trend_program_names(
    current_user: UserResponse,
    program_name: Optional[str],
) -> Tuple[Optional[List[str]], Optional[str]]:
    """Same semantics as /assets/common/trends and /findings/common/trends."""
    program_names_list: Optional[List[str]] = None
    selected_name: Optional[str] = None

    if program_name:
        selected_name = program_name
        if not current_user.is_superuser and "admin" not in current_user.roles:
            user_programs = current_user.program_permissions.keys()
            if program_name not in user_programs:
                raise HTTPException(status_code=403, detail=f"Access denied to program '{program_name}'")
        program = await ProgramRepository.get_program_by_name(program_name)
        if not program:
            logger.warning(
                "Program '%s' not found for dashboard trends; returning empty buckets",
                program_name,
            )
            program_names_list = [_EMPTY_TREND_PROGRAM_SCOPE]
        else:
            program_names_list = [program_name]
    else:
        accessible_programs = get_user_accessible_programs(current_user)
        if accessible_programs:
            program_names_list = list(accessible_programs)
        else:
            program_names_list = None

    return program_names_list, selected_name


def _restricted_latest_program_scope(
    current_user: UserResponse,
    program_name: Optional[str],
) -> Tuple[Optional[str], Optional[List[str]], bool]:
    """
    Returns (program_name, restrict_to_program_names, deny_no_access).

    When deny_no_access, latest widgets should be empty (user has no program access).
    """
    unrestricted = current_user.is_superuser or "admin" in current_user.roles
    if program_name:
        if not unrestricted:
            accessible = get_user_accessible_programs(current_user)
            if accessible and program_name not in accessible:
                raise HTTPException(status_code=403, detail=f"Access denied to program '{program_name}'")
        return program_name, None, False

    if unrestricted:
        return None, None, False

    accessible = list(get_user_accessible_programs(current_user))
    if not accessible:
        return None, [], True
    return None, accessible, False


async def _asset_stats_bundle(current_user: UserResponse, program_name: Optional[str]):
    if program_name:
        if not current_user.is_superuser and "admin" not in current_user.roles:
            user_programs = current_user.program_permissions.keys()
            if program_name not in user_programs:
                raise HTTPException(status_code=403, detail=f"Access denied to program '{program_name}'")
        return await CommonAssetsRepository.get_detailed_asset_stats({"program_name": program_name})
    accessible = get_user_accessible_programs(current_user)
    if accessible:
        return await CommonAssetsRepository.get_aggregated_asset_stats(accessible)
    return await CommonAssetsRepository.get_aggregated_asset_stats()


async def _findings_stats_bundle(current_user: UserResponse, program_name: Optional[str]):
    if program_name:
        if not current_user.is_superuser and "admin" not in current_user.roles:
            user_programs = current_user.program_permissions.keys()
            if program_name not in user_programs:
                raise HTTPException(status_code=403, detail=f"Access denied to program '{program_name}'")
        return await CommonFindingsRepository.get_detailed_findings_stats({"program_name": program_name})
    accessible = get_user_accessible_programs(current_user)
    if accessible:
        return await CommonFindingsRepository.get_aggregated_findings_stats(accessible)
    return await CommonFindingsRepository.get_aggregated_findings_stats()


def _tech_program_filter(current_user: UserResponse, program_name: Optional[str]) -> Optional[List[str]]:
    """program_filter list for UrlAssetsRepository (None = all programs)."""
    unrestricted = current_user.is_superuser or "admin" in current_user.roles
    if program_name:
        return [program_name]
    if unrestricted:
        return None
    acc = get_user_accessible_programs(current_user)
    return acc if acc else []


@router.get("/summary")
async def get_dashboard_summary(
    program_name: Optional[str] = Query(None, description="Filter to a single program"),
    latest_limit: int = Query(10, ge=1, le=20),
    days: int = Query(30, ge=1, le=366),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    current_user: UserResponse = Depends(get_current_user_from_middleware),
):
    """Single payload for dashboard first paint (threadpool-backed sub-queries)."""
    sd = _parse_iso_date_optional(start_date, "start_date")
    ed = _parse_iso_date_optional(end_date, "end_date")
    if (sd is None) ^ (ed is None):
        raise HTTPException(
            status_code=400,
            detail="Both start_date and end_date are required for a custom range",
        )

    program_names_trend, _ = await _resolve_trend_program_names(current_user, program_name)

    la_program, la_restrict, la_deny = _restricted_latest_program_scope(current_user, program_name)
    latest_assets_empty: Dict[str, Any] = {"subdomains": [], "urls": []}
    latest_findings_empty: Dict[str, Any] = {"nuclei": [], "typosquat": [], "wpscan": []}

    workflow_filter: Dict[str, Any] = {}
    if program_name:
        workflow_filter["program_name"] = program_name
    wf_query = filter_by_user_programs(workflow_filter, current_user)
    sanitized_wf = await WorkflowRepository.sanitize_query(wf_query)

    tech_filter = _tech_program_filter(current_user, program_name)

    async def safe_asset_stats():
        try:
            return await _asset_stats_bundle(current_user, program_name)
        except Exception as exc:
            logger.exception("dashboard asset stats: %s", exc)
            return exc

    async def safe_findings_stats():
        try:
            return await _findings_stats_bundle(current_user, program_name)
        except Exception as exc:
            logger.exception("dashboard findings stats: %s", exc)
            return exc

    async def safe_asset_trends():
        try:
            return await CommonAssetsRepository.get_asset_trends(
                program_names=program_names_trend,
                start_day=sd,
                end_day=ed,
                days=days,
            )
        except Exception as exc:
            logger.exception("dashboard asset trends: %s", exc)
            return exc

    async def safe_findings_trends():
        try:
            return await CommonFindingsRepository.get_findings_trends(
                program_names=program_names_trend,
                start_day=sd,
                end_day=ed,
                days=days,
            )
        except Exception as exc:
            logger.exception("dashboard findings trends: %s", exc)
            return exc

    async def safe_latest_assets():
        if la_deny:
            return latest_assets_empty
        try:
            return await CommonAssetsRepository.get_latest_assets(
                la_program,
                latest_limit,
                None,
                ["subdomains", "urls"],
                la_restrict,
            )
        except Exception as exc:
            logger.exception("dashboard latest assets: %s", exc)
            return exc

    async def safe_latest_findings():
        if la_deny:
            return latest_findings_empty
        try:
            return await CommonFindingsRepository.get_latest_findings(
                la_program,
                latest_limit,
                None,
                ["nuclei", "typosquat", "wpscan"],
                la_restrict,
            )
        except Exception as exc:
            logger.exception("dashboard latest findings: %s", exc)
            return exc

    async def safe_recent_workflows():
        try:
            raw = await WorkflowRepository.execute_query(
                sanitized_wf,
                limit=8,
                skip=0,
                sort={"created_at": -1},
                lite=True,
            )
            return transform_workflow_executions_for_status_list(raw)
        except Exception as exc:
            logger.exception("dashboard recent workflows: %s", exc)
            return exc

    async def safe_active_wf():
        try:
            return await WorkflowRepository.count_active_workflow_logs(sanitized_wf)
        except Exception as exc:
            logger.exception("dashboard active workflows: %s", exc)
            return exc

    async def safe_tech():
        try:
            if tech_filter == []:
                return {
                    "status": "success",
                    "items": [],
                    "pagination": {
                        "total_items": 0,
                        "total_pages": 0,
                        "current_page": 1,
                        "page_size": 10,
                        "has_next": False,
                        "has_prev": False,
                    },
                }
            return await UrlAssetsRepository.get_technologies_with_urls(
                program_filter=tech_filter,
                page=1,
                page_size=10,
                search=None,
                sort_by="count",
                sort_order="desc",
            )
        except Exception as exc:
            logger.exception("dashboard technologies: %s", exc)
            return exc

    async def safe_queue():
        try:
            return await run_in_threadpool(k8s_service.check_queue_capacity)
        except Exception as exc:
            logger.exception("dashboard queue: %s", exc)
            return exc

    results = await asyncio.gather(
        safe_asset_stats(),
        safe_findings_stats(),
        safe_asset_trends(),
        safe_findings_trends(),
        safe_latest_assets(),
        safe_latest_findings(),
        safe_recent_workflows(),
        safe_active_wf(),
        safe_tech(),
        safe_queue(),
    )

    keys = [
        "asset_stats",
        "findings_stats",
        "asset_trends",
        "findings_trends",
        "latest_assets",
        "latest_findings",
        "workflow_executions",
        "active_workflows",
        "technologies_summary",
        "queue_status",
    ]
    payload: Dict[str, Any] = {"status": "success", "errors": {}}
    for key, result in zip(keys, results):
        if isinstance(result, Exception):
            payload["errors"][key] = str(result)
            payload[key] = None
        else:
            payload[key] = result

    asset_stats = payload.get("asset_stats")
    total_programs = 0
    if asset_stats is not None:
        if hasattr(asset_stats, "total_programs"):
            total_programs = int(asset_stats.total_programs or 0)
        elif isinstance(asset_stats, dict):
            total_programs = int(asset_stats.get("total_programs") or 0)

    payload["total_programs"] = total_programs

    for k in ("asset_stats", "findings_stats", "asset_trends", "findings_trends"):
        if payload.get(k) is not None and hasattr(payload[k], "model_dump"):
            payload[k] = payload[k].model_dump()

    return payload
