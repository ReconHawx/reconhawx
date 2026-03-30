"""Built-in event handler definitions (API-side only).

Merge order for effective handlers (see ``EventHandlerConfigRepository.get_effective_config``):

1. **System** — this module / ``system_event_handlers.yaml``; stable ids; not editable in UI;
   cannot be overridden by program managers (same id is ignored from lower layers).
2. **Global** — rows in ``event_handler_configs`` where ``program_id`` IS NULL (admin UI).
3. **Program addons** — when ``programs.event_handler_addon_mode`` is true, rows for that program;
   ids must not collide with system ids (filtered on save).
4. **Notification handlers** — generated from ``programs.notification_settings`` at read time
   (``notify_*`` ids); not persisted in ``event_handler_configs``.

**Legacy programs** (``event_handler_addon_mode`` false with stored rows): effective list is
system + stored program rows (with ``notify_*`` and legacy Discord ids stripped from storage
when notification settings sync runs) + ephemeral notification handlers from settings.

Dedup rule: first occurrence wins by handler ``id`` when concatenating layers.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Set

logger = logging.getLogger(__name__)

_CONFIG_DIR = Path(__file__).resolve().parent
_SYSTEM_YAML = _CONFIG_DIR / "system_event_handlers.yaml"
_GLOBAL_DEFAULT_YAML = _CONFIG_DIR / "global_default_event_handlers.yaml"


def _load_handlers_yaml(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        logger.warning("Event handler YAML missing: %s", path)
        return []
    try:
        import yaml

        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        handlers = data.get("handlers", []) if data else []
        return [h for h in handlers if isinstance(h, dict) and h.get("id")]
    except Exception as e:
        logger.warning("Could not load %s: %s", path, e)
        return []


def get_system_handlers() -> List[Dict[str, Any]]:
    """Mandatory handlers (read-only in admin UI)."""
    return list(_load_handlers_yaml(_SYSTEM_YAML))


def get_system_handler_ids() -> Set[str]:
    return {h["id"] for h in get_system_handlers() if h.get("id")}


def get_global_bootstrap_handlers() -> List[Dict[str, Any]]:
    """Seed global DB when no global rows exist (admin-editable copy in DB after seed)."""
    return list(_load_handlers_yaml(_GLOBAL_DEFAULT_YAML))
