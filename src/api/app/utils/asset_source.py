"""Normalize asset discovery source values for ingest and persistence."""

from typing import Any, Optional


def normalize_asset_source(value: Any) -> Optional[str]:
    """Return a stripped source string (max 255) or None if empty/invalid."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:255]


def apply_lazy_source(existing_source: Optional[str], incoming_source: Optional[str]) -> Optional[str]:
    """Write-once: keep existing source; lazy-fill when existing is NULL."""
    if existing_source:
        return existing_source
    return incoming_source
