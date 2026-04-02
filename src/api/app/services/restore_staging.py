"""Ephemeral on-disk staging for database restore dumps (consumed by a Kubernetes Job)."""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from secrets import token_hex, token_urlsafe
from typing import Optional

logger = logging.getLogger(__name__)

STAGING_TTL_SEC = int(os.getenv("DATABASE_RESTORE_STAGING_TTL_SEC", "86400"))

_lock = threading.Lock()
# staging_id -> StagedFile
_staging: dict[str, "StagedFile"] = {}


@dataclass
class StagedFile:
    path: str
    pull_token: str
    created: float


def _purge_stale_locked() -> None:
    now = time.time()
    for sid, sf in list(_staging.items()):
        if now - sf.created > STAGING_TTL_SEC:
            _unlink_safe(sf.path)
            del _staging[sid]
            logger.info("removed stale restore staging id=%s", sid)


def _unlink_safe(path: str) -> None:
    try:
        os.unlink(path)
    except OSError as e:
        logger.warning("could not unlink staging file %s: %s", path, e)


def purge_stale() -> None:
    with _lock:
        _purge_stale_locked()


def register_file(abs_path: str) -> tuple[str, str]:
    """Register a staged dump path. Returns (staging_id, pull_token)."""
    purge_stale()
    staging_id = token_hex(16)
    pull_token = token_urlsafe(32)
    with _lock:
        _purge_stale_locked()
        _staging[staging_id] = StagedFile(
            path=abs_path,
            pull_token=pull_token,
            created=time.time(),
        )
    return staging_id, pull_token


def get_staging(staging_id: str) -> Optional[StagedFile]:
    with _lock:
        _purge_stale_locked()
        return _staging.get(staging_id)


def resolve_pull_token(token: str) -> Optional[str]:
    with _lock:
        _purge_stale_locked()
        for sf in _staging.values():
            if sf.pull_token == token:
                return sf.path
    return None


def finalize_staging_id(staging_id: str) -> None:
    """Remove staging metadata and delete the file if present."""
    with _lock:
        sf = _staging.pop(staging_id, None)
    if sf:
        _unlink_safe(sf.path)
