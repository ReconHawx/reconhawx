"""Internal-only: Job initContainer pulls staged dump via one-time token."""

import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from auth.dependencies import require_internal_service_identity
from models.user_postgres import UserResponse
from services import restore_staging

logger = logging.getLogger(__name__)

internal_router = APIRouter(tags=["internal-database-restore"])


@internal_router.get("/database-restore/pull")
async def pull_staged_restore_dump(
    token: str = Query(..., min_length=16),
    _user: UserResponse = Depends(require_internal_service_identity),
):
    path = restore_staging.resolve_pull_token(token)
    if not path or not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Invalid or expired staging token")
    return FileResponse(path, media_type="application/octet-stream", filename="dump")
