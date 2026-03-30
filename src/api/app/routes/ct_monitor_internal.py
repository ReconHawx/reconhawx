"""Internal routes for ct-monitor service (internal service token only)."""

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from auth.dependencies import require_internal_service_identity
from models.user_postgres import UserResponse
from services.ct_monitor_runtime_settings import get_ct_monitor_runtime_merged
import logging

logger = logging.getLogger(__name__)

internal_ct_monitor_router = APIRouter(tags=["internal-ct-monitor"])


@internal_ct_monitor_router.get("/ct-monitor/runtime-settings", response_model=Dict[str, Any])
async def get_ct_monitor_runtime_settings_internal(
    _user: UserResponse = Depends(require_internal_service_identity),
):
    """Merged CT monitor runtime intervals/poll settings for ct-monitor pods."""
    try:
        settings = await get_ct_monitor_runtime_merged()
        return {"status": "success", "settings": settings}
    except Exception as e:
        logger.error("Error reading ct_monitor_runtime: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
