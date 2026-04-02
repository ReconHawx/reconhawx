"""Superuser database backup endpoints."""

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from auth.dependencies import require_superuser
from models.user_postgres import UserResponse
from repository.action_log_repo import ActionLogRepository
from services import database_backup_service as dbs

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/database/status")
async def get_database_backup_status(
    current_user: UserResponse = Depends(require_superuser),
):
    """
    Database metadata and pg client availability (superuser).
    """
    try:
        data = await dbs.get_database_status()
        return {"status": "success", **data}
    except Exception as e:
        logger.error("database status error: %s", e)
        raise HTTPException(status_code=500, detail="Could not read database status") from e


@router.get("/database/backup")
async def download_database_backup(
    format: Literal["custom", "plain"] = Query("custom", description="custom (-Fc) or plain SQL (-Fp)"),
    current_user: UserResponse = Depends(require_superuser),
):
    """
    Download a pg_dump of the application database (superuser).
    Streams a temp file produced by pg_dump after the dump completes successfully.
    """
    try:
        path = await dbs.run_pg_dump_to_tempfile(format)
    except RuntimeError as e:
        logger.error("pg_dump failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e
    except Exception as e:
        logger.exception("unexpected pg_dump error: %s", e)
        raise HTTPException(status_code=500, detail="Backup failed") from e

    filename = dbs.backup_filename_prefix(format)
    logger.warning(
        "database backup download started user_id=%s email=%s format=%s",
        getattr(current_user, "id", None),
        getattr(current_user, "email", None),
        format,
    )

    await ActionLogRepository.log_action(
        entity_type="system",
        entity_id="database",
        action_type="database_backup_download",
        user_id=str(current_user.id),
        metadata={"format": format, "filename": filename},
    )

    return StreamingResponse(
        dbs.iter_backup_file_chunks(path),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
