from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any, Optional
import logging
from pydantic import BaseModel
from repository.action_log_repo import ActionLogRepository
from auth.dependencies import get_current_user_from_middleware, get_internal_service_user
from models.user_postgres import UserResponse

logger = logging.getLogger(__name__)
router = APIRouter()


async def require_internal_service_auth(
    internal_user: Optional[UserResponse] = Depends(get_internal_service_user)
) -> UserResponse:
    """
    Require internal service authentication only.
    This endpoint is for internal service use only.
    """
    if not internal_user:
        raise HTTPException(
            status_code=403,
            detail="This endpoint requires internal service authentication"
        )
    return internal_user


class ActionLogCreateRequest(BaseModel):
    entity_type: str
    entity_id: str
    action_type: str
    user_id: str
    old_value: Optional[Dict[str, Any]] = None
    new_value: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None


@router.post("", response_model=Dict[str, Any])
async def create_action_log(
    request: ActionLogCreateRequest,
    _: UserResponse = Depends(require_internal_service_auth)
):
    """
    Create a new action log entry.

    This endpoint is for internal service use only and requires internal service authentication.
    Used by background jobs and other services to log actions performed on entities.
    """
    try:
        log_id = await ActionLogRepository.log_action(
            entity_type=request.entity_type,
            entity_id=request.entity_id,
            action_type=request.action_type,
            user_id=request.user_id,
            old_value=request.old_value,
            new_value=request.new_value,
            metadata=request.metadata
        )

        if not log_id:
            raise HTTPException(status_code=500, detail="Failed to create action log")

        return {
            "status": "success",
            "message": "Action log created successfully",
            "log_id": log_id
        }

    except Exception as e:
        logger.error(f"Error creating action log: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error creating action log: {str(e)}")


@router.get("/entity/{entity_type}/{entity_id}", response_model=Dict[str, Any])
async def get_action_logs_for_entity(
    entity_type: str,
    entity_id: str,
    limit: int = 50,
    offset: int = 0,
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """
    Get action logs for a specific entity.

    Returns a paginated list of action logs for the specified entity.
    """
    try:
        if limit > 100:
            limit = 100  # Cap at 100 for performance

        action_logs = await ActionLogRepository.get_action_logs_for_entity(
            entity_type=entity_type,
            entity_id=entity_id,
            limit=limit,
            offset=offset
        )

        return {
            "status": "success",
            "message": f"Found {len(action_logs)} action logs for entity {entity_type} {entity_id}",
            "items": action_logs,
            "pagination": {
                "limit": limit,
                "offset": offset,
                "count": len(action_logs)
            }
        }

    except Exception as e:
        logger.error(f"Error getting action logs for entity {entity_type} {entity_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting action logs: {str(e)}")


@router.get("/user/{user_id}", response_model=Dict[str, Any])
async def get_user_actions(
    user_id: str,
    entity_type: Optional[str] = None,
    action_type: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """
    Get actions performed by a specific user.

    Returns a paginated list of actions performed by the specified user.
    Can be filtered by entity_type and action_type.
    """
    try:
        # Users can only see their own actions unless they are admin/superuser
        if not (current_user.is_superuser or "admin" in current_user.roles) and current_user.id != user_id:
            raise HTTPException(status_code=403, detail="Not authorized to view other users' actions")

        if limit > 100:
            limit = 100  # Cap at 100 for performance

        action_logs = await ActionLogRepository.get_user_actions(
            user_id=user_id,
            entity_type=entity_type,
            action_type=action_type,
            limit=limit,
            offset=offset
        )

        return {
            "status": "success",
            "message": f"Found {len(action_logs)} actions for user {user_id}",
            "items": action_logs,
            "filters": {
                "entity_type": entity_type,
                "action_type": action_type
            },
            "pagination": {
                "limit": limit,
                "offset": offset,
                "count": len(action_logs)
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user actions for user {user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting user actions: {str(e)}")