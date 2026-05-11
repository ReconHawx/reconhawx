"""Stable fingerprint helpers for unified scanner findings (must match Alembic backfill SQL)."""

from __future__ import annotations

import hashlib
from typing import Any, Optional
from uuid import UUID


def _norm_str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, UUID):
        return str(v)
    return str(v).strip() if isinstance(v, str) else str(v)


def fingerprint_nuclei(
    *,
    url: Optional[str],
    template_id: Optional[str],
    matcher_name: Optional[str],
    program_id: Any,
    matched_at: Optional[str],
) -> str:
    parts = [
        _norm_str(url),
        _norm_str(template_id),
        _norm_str(matcher_name),
        _norm_str(program_id),
        _norm_str(matched_at),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def fingerprint_wpscan(*, url: Optional[str], item_name: Optional[str], program_id: Any) -> str:
    parts = [_norm_str(url), _norm_str(item_name), _norm_str(program_id)]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def fingerprint_broken_link(*, program_id: Any, url: Optional[str]) -> str:
    parts = [_norm_str(program_id), _norm_str(url)]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
