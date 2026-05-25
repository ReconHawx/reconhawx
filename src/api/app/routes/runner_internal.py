"""Internal runner routes (last-execution / eligible assets)."""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, Field

from auth.dependencies import require_internal_service_identity
from models.user_postgres import UserResponse
from repository.task_last_executions_repo import (
    TaskLastExecutionsRepository,
    normalize_asset_type,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["internal-runner"])


class EligibleAssetsRequest(BaseModel):
    program_id: uuid.UUID
    task_type: str = Field(..., min_length=1)
    params: Dict[str, Any] = Field(default_factory=dict)
    threshold_hours: int = Field(..., ge=1)
    limit: int = Field(..., ge=1, le=10000)
    page: int = Field(default=1, ge=1)
    filter_type: Optional[str] = None
    sort_by: str = "updated_at"
    sort_dir: Literal["asc", "desc"] = "desc"


class RecentTargetsRequest(BaseModel):
    program_id: uuid.UUID
    task_type: str = Field(..., min_length=1)
    params: Dict[str, Any] = Field(default_factory=dict)
    threshold_hours: int = Field(..., ge=1)
    targets: List[str] = Field(default_factory=list)


@router.post("/assets/{asset_type}/eligible-for-task", response_model=Dict[str, Any])
async def eligible_assets_for_task(
    asset_type: str = Path(..., description="subdomain, ip, url, apex-domain, service, certificate"),
    request: EligibleAssetsRequest = ...,
    _user: UserResponse = Depends(require_internal_service_identity),
):
    try:
        normalize_asset_type(asset_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    skip = (request.page - 1) * request.limit
    try:
        result = await TaskLastExecutionsRepository.search_eligible_assets(
            asset_type=asset_type,
            program_id=request.program_id,
            task_type=request.task_type,
            params=request.params,
            threshold_hours=request.threshold_hours,
            limit=request.limit,
            skip=skip,
            filter_type=request.filter_type,
            sort_by=request.sort_by,
            sort_dir=request.sort_dir,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("eligible-for-task failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    total_count = result.get("total_count", 0)
    page_size = request.limit
    total_pages = (total_count + page_size - 1) // page_size if page_size > 0 else 1
    return {
        "status": "success",
        "pagination": {
            "total_items": total_count,
            "total_pages": total_pages,
            "current_page": request.page,
            "page_size": page_size,
            "has_next": request.page < total_pages,
            "has_previous": request.page > 1,
        },
        "items": result.get("items", []),
    }


@router.post("/task-executions/recent-targets", response_model=Dict[str, Any])
async def recent_targets(
    request: RecentTargetsRequest,
    _user: UserResponse = Depends(require_internal_service_identity),
):
    try:
        recent = await TaskLastExecutionsRepository.filter_recent_targets(
            program_id=request.program_id,
            task_type=request.task_type,
            params=request.params,
            threshold_hours=request.threshold_hours,
            targets=request.targets,
        )
        return {"status": "success", "recent_targets": recent}
    except Exception as exc:
        logger.exception("recent-targets failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
