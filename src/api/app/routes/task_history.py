"""Per-asset workflow task execution history."""

import uuid
from typing import Any, Dict, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status

from auth.dependencies import check_program_permission_by_id, get_current_user_from_middleware
from models.user_postgres import UserResponse
from repository.task_history_repo import TaskHistoryRepository

router = APIRouter()

AssetTypeParam = Literal[
    "subdomain",
    "apex_domain",
    "ip",
    "url",
    "service",
    "certificate",
]


@router.get("/{asset_type}/{asset_id}/task-history", response_model=Dict[str, Any])
async def get_asset_task_history(
    asset_type: AssetTypeParam,
    asset_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    current_user: UserResponse = Depends(get_current_user_from_middleware),
):
    try:
        aid = uuid.UUID(asset_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")

    program_id = await TaskHistoryRepository.get_asset_program_id(asset_type, asset_id)
    if program_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")

    if not await check_program_permission_by_id(current_user, str(program_id), "analyst"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")

    skip = (page - 1) * page_size
    items, total = await TaskHistoryRepository.get_task_history(
        asset_type=asset_type,
        asset_id=aid,
        program_id=program_id,
        limit=page_size,
        skip=skip,
    )

    total_pages = (total + page_size - 1) // page_size if page_size > 0 else 1

    return {
        "status": "success",
        "pagination": {
            "total_items": total,
            "total_pages": total_pages,
            "current_page": page,
            "page_size": page_size,
            "has_next": page < total_pages,
            "has_previous": page > 1,
        },
        "items": items,
    }
