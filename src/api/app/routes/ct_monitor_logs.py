"""Searchable CT monitor activity logs."""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException

from auth.dependencies import get_current_user_from_middleware, get_user_accessible_programs
from models.ct_monitor_log import CtMonitorLogSearchRequest
from models.user_postgres import UserResponse
from repository.ct_monitor_logs_repo import CtMonitorLogsRepository

logger = logging.getLogger(__name__)

router = APIRouter()


def _program_filter_for_user(
    request_program: Any,
    current_user: UserResponse,
) -> Optional[List[str]]:
    requested: Optional[List[str]] = None
    if isinstance(request_program, str) and request_program.strip():
        requested = [request_program.strip()]
    elif isinstance(request_program, list):
        requested = [p.strip() for p in request_program if isinstance(p, str) and p.strip()]

    unrestricted = current_user.is_superuser or "admin" in current_user.roles
    if unrestricted:
        return requested if requested else None

    allowed = get_user_accessible_programs(current_user) or []
    if not allowed:
        return []

    if requested:
        return [program for program in requested if program in allowed]

    return allowed


def _empty_paginated_response(request: CtMonitorLogSearchRequest) -> Dict[str, Any]:
    return {
        "status": "success",
        "pagination": {
            "total_items": 0,
            "total_pages": 1,
            "current_page": request.page,
            "page_size": request.page_size,
            "has_next": False,
            "has_previous": False,
        },
        "items": [],
    }


@router.post("/logs/search", response_model=Dict[str, Any])
async def search_ct_monitor_logs(
    request: CtMonitorLogSearchRequest,
    current_user: UserResponse = Depends(get_current_user_from_middleware),
):
    """Search durable CT monitor logs with program access enforcement."""
    try:
        programs = _program_filter_for_user(request.program, current_user)
        if programs == []:
            return _empty_paginated_response(request)

        skip = (request.page - 1) * request.page_size
        result = await CtMonitorLogsRepository.search_logs_typed(
            programs=programs,
            event_type=request.event_type,
            outcome=request.outcome,
            search=request.search,
            match_type=request.match_type,
            priority=request.priority,
            start_time=request.start_time,
            end_time=request.end_time,
            sort_by=request.sort_by,
            sort_dir=request.sort_dir,
            limit=request.page_size,
            skip=skip,
        )

        total_count = int(result.get("total_count", 0))
        total_pages = (total_count + request.page_size - 1) // request.page_size if request.page_size > 0 else 1
        return {
            "status": "success",
            "pagination": {
                "total_items": total_count,
                "total_pages": total_pages,
                "current_page": request.page,
                "page_size": request.page_size,
                "has_next": request.page < total_pages,
                "has_previous": request.page > 1,
            },
            "items": result.get("items", []),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error searching CT monitor logs: %s", e)
        raise HTTPException(status_code=500, detail="Failed to search CT monitor logs")
