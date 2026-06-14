"""Internal routes for ct-monitor service (internal service token only)."""

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from auth.dependencies import require_internal_service_identity
from models.ct_monitor_log import CtMonitorLogIngestRequest
from models.user_postgres import UserResponse
from repository.ct_monitor_logs_repo import CtMonitorLogsRepository
from services.ct_monitor_runtime_settings import get_ct_monitor_runtime_merged

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


@internal_ct_monitor_router.post("/ct-monitor/logs", response_model=Dict[str, Any])
async def ingest_ct_monitor_logs_internal(
    request: CtMonitorLogIngestRequest,
    _user: UserResponse = Depends(require_internal_service_identity),
):
    """Persist batched CT monitor decisions for the admin CT logs page."""
    try:
        result = await CtMonitorLogsRepository.insert_logs(request.logs)
        status_value = "success" if result.get("error_count", 0) == 0 else "partial_success"
        return {"status": status_value, "data": result}
    except Exception as e:
        logger.exception("Error ingesting ct_monitor_logs: %s", e)
        raise HTTPException(status_code=500, detail="Failed to ingest CT monitor logs")
