"""Internal-only: upgrade Job init pulls staged tarball via one-time token."""

import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from auth.dependencies import require_internal_service_identity
from models.user_postgres import UserResponse
from services import upgrade_staging

logger = logging.getLogger(__name__)

internal_router = APIRouter(tags=["internal-upgrade"])


@internal_router.get("/upgrade/pull")
async def pull_staged_upgrade_tarball(
    token: str = Query(..., min_length=16),
    _user: UserResponse = Depends(require_internal_service_identity),
):
    path = upgrade_staging.resolve_pull_token(token)
    if not path or not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Invalid or expired staging token")
    return FileResponse(path, media_type="application/gzip", filename="upgrade.tar.gz")
