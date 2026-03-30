"""Event handler configuration routes: admin (superuser), program (manager), and internal (event-handler service)."""

from fastapi import APIRouter, HTTPException, Depends, Body, Query
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

from auth.dependencies import (
    require_superuser,
    require_internal_service_or_authentication,
)
from models.user_postgres import UserResponse
from repository import EventHandlerConfigRepository
import logging

logger = logging.getLogger(__name__)

# Admin router: /admin/event-handler-configs (superuser)
admin_router = APIRouter(tags=["admin-event-handler-config"])


class EventHandlerConfigUpdateRequest(BaseModel):
    """Request model for updating event handler config"""
    handlers: List[Dict[str, Any]] = Field(..., description="Array of handler configs (global layer; system handlers are API-defined)")


@admin_router.get("/event-handler-configs", response_model=Dict[str, Any])
async def get_global_event_handler_config(
    current_user: UserResponse = Depends(require_superuser)
):
    """Get global event handler config (superuser only)."""
    try:
        handlers = await EventHandlerConfigRepository.get_global_handlers()
        return {"status": "success", "handlers": handlers}
    except Exception as e:
        logger.error(f"Error getting global event handler config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@admin_router.put("/event-handler-configs", response_model=Dict[str, Any])
async def update_global_event_handler_config(
    request: EventHandlerConfigUpdateRequest = Body(...),
    current_user: UserResponse = Depends(require_superuser)
):
    """Update global event handler config (superuser only)."""
    try:
        await EventHandlerConfigRepository.set_global_config(request.handlers)
        return {"status": "success", "message": "Global event handler config updated"}
    except Exception as e:
        logger.error(f"Error updating global event handler config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@admin_router.get("/event-handler-configs/defaults", response_model=Dict[str, Any])
async def get_default_event_handler_config(
    current_user: UserResponse = Depends(require_superuser)
):
    """Get default global handler list used to seed empty DB (superuser only). Excludes system handlers."""
    try:
        from repository.event_handler_config_repo import get_default_handlers

        handlers = get_default_handlers()
        return {"status": "success", "handlers": handlers}
    except Exception as e:
        logger.error(f"Error getting default event handler config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@admin_router.get("/event-handler-configs/system", response_model=Dict[str, Any])
async def get_system_event_handler_config(
    current_user: UserResponse = Depends(require_superuser),
):
    """List mandatory system handlers (read-only; defined in API config)."""
    try:
        from config.event_handler_builtins import get_system_handlers

        handlers = get_system_handlers()
        return {"status": "success", "handlers": handlers}
    except Exception as e:
        logger.error(f"Error getting system event handler config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Internal router: /internal/event-handler-configs (internal service token)
internal_router = APIRouter(tags=["internal-event-handler-config"])


@internal_router.get("/event-handler-configs", response_model=Dict[str, Any])
async def get_effective_event_handler_config(
    program_name: Optional[str] = Query(None, description="Program name for effective config (omit for global)"),
    current_user: UserResponse = Depends(require_internal_service_or_authentication)
):
    """
    Effective handlers for the event-handler service: system + global (+ program layer) +
    generated notification handlers. See ``event_handler_config_repo`` module docstring.
    """
    try:
        handlers = await EventHandlerConfigRepository.get_effective_config(program_name)
        return {"status": "success", "handlers": handlers}
    except Exception as e:
        logger.error(f"Error getting effective event handler config: {e}")
        raise HTTPException(status_code=500, detail=str(e))
