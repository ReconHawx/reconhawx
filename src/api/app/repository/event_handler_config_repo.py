"""Repository for event handler configuration (global and per-program).

Effective handler list for a program (used by the event-handler service via internal API):

1. **System** — ``config/system_event_handlers.yaml`` + ``event_handler_builtins``; not stored in DB;
   stable ids; first in merge order.
2. **Global** — ``event_handler_configs`` rows with ``program_id`` NULL (admin-editable).
3. **Program addons** — when ``programs.event_handler_addon_mode`` is true, per-program rows;
   merged after global; duplicate ids are dropped (system/global win).
4. **Notifications** — ``notify_*`` handlers from ``generate_handlers_from_notification_settings``;
   not persisted; appended last.

**Legacy** programs (``event_handler_addon_mode`` false with stored rows): the stored list is a
full snapshot (formerly including a copy of global). Effective = system + that snapshot
(stripped of ``notify_*``, legacy Discord-only ids, and ids that collide with system) + fresh
notifications from settings.

Dedup: concatenation order above, then **first handler per id wins**.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set
import logging

from db import get_db_session
from models.postgres import EventHandlerConfig, Program

from config.event_handler_builtins import get_global_bootstrap_handlers, get_system_handler_ids, get_system_handlers

logger = logging.getLogger(__name__)

# Discord-only handlers removed from global defaults (now program-specific via notification settings)
_DISCORD_HANDLER_IDS = {
    "ct_typosquat_alert_notification",
    "subdomain_created_resolved_notification",
    "subdomain_resolved_notification_updated",
}

_NOTIFY_HANDLER_PREFIX = "notify_"


def _dedupe_handlers_keep_first(handlers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: Set[str] = set()
    out: List[Dict[str, Any]] = []
    for h in handlers:
        hid = (h.get("id") or "").strip()
        if not hid or hid in seen:
            continue
        seen.add(hid)
        out.append(h)
    return out


def _is_notify_handler_id(handler_id: Optional[str]) -> bool:
    return bool(handler_id) and str(handler_id).startswith(_NOTIFY_HANDLER_PREFIX)


def get_default_handlers() -> List[Dict[str, Any]]:
    """Bootstrap list for global seed and admin "defaults" endpoint (excludes system handlers)."""
    return list(get_global_bootstrap_handlers())


def _handler_to_row(handler: Dict[str, Any]) -> Dict[str, Any]:
    """Extract handler_id, event_type, config from handler dict."""
    handler_id = handler.get("id") or ""
    event_type = handler.get("event_type") or ""
    config = {k: v for k, v in handler.items() if k not in ("id", "event_type")}
    return {"handler_id": handler_id, "event_type": event_type, "config": config}


def _rows_to_handlers(rows: List[EventHandlerConfig]) -> List[Dict[str, Any]]:
    """Convert list of rows to handler dicts."""
    return [r.to_handler_dict() for r in rows]


class EventHandlerConfigRepository:
    """Repository for event handler configuration (one row per handler)."""

    @staticmethod
    def _filter_discord_handlers(handlers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove legacy Discord-only handlers (now created per-program via notification settings)."""
        return [h for h in handlers if h.get("id") not in _DISCORD_HANDLER_IDS]

    @staticmethod
    def filter_handlers_for_program_persist(handlers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Strip ids that must not be stored on programs (system, notify)."""
        system_ids = get_system_handler_ids()
        out: List[Dict[str, Any]] = []
        for h in handlers:
            hid = (h.get("id") or "").strip()
            if not hid or hid in system_ids or _is_notify_handler_id(hid):
                continue
            out.append(h)
        return out

    @staticmethod
    def filter_handlers_for_global_persist(handlers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Strip system handler ids from admin global save payload."""
        system_ids = get_system_handler_ids()
        return [h for h in handlers if (h.get("id") or "").strip() not in system_ids]

    @staticmethod
    async def get_global_config() -> Optional[Dict[str, Any]]:
        """Get global handler config. Returns None if not set (no rows)."""
        handlers = await EventHandlerConfigRepository.get_global_handlers()
        if not handlers:
            return None
        return {"handlers": handlers, "program_id": None}

    @staticmethod
    async def get_global_handlers() -> List[Dict[str, Any]]:
        """Global handlers from DB only; seed from API bootstrap YAML if empty. Not merged with system."""
        async with get_db_session() as db:
            rows = db.query(EventHandlerConfig).filter(EventHandlerConfig.program_id.is_(None)).all()
            if rows:
                handlers = _rows_to_handlers(rows)
                return EventHandlerConfigRepository._filter_discord_handlers(handlers)
            defaults = get_global_bootstrap_handlers()
            if defaults:
                try:
                    for h in defaults:
                        if not h.get("id"):
                            continue
                        rd = _handler_to_row(h)
                        db.add(
                            EventHandlerConfig(
                                program_id=None,
                                handler_id=rd["handler_id"],
                                event_type=rd["event_type"],
                                config=rd["config"],
                            )
                        )
                    db.commit()
                    logger.info("Seeded global event handler config with %s handlers", len(defaults))
                    return EventHandlerConfigRepository._filter_discord_handlers(defaults)
                except Exception as e:
                    db.rollback()
                    logger.warning("Failed to seed global config: %s", e)
            return EventHandlerConfigRepository._filter_discord_handlers(defaults) if defaults else []

    @staticmethod
    async def set_global_config(handlers: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Set global handler config. Replaces all global rows. System handlers are ignored if present."""
        cleaned = EventHandlerConfigRepository.filter_handlers_for_global_persist(handlers)
        async with get_db_session() as db:
            db.query(EventHandlerConfig).filter(EventHandlerConfig.program_id.is_(None)).delete()
            for h in cleaned:
                if not h.get("id"):
                    continue
                rd = _handler_to_row(h)
                db.add(
                    EventHandlerConfig(
                        program_id=None,
                        handler_id=rd["handler_id"],
                        event_type=rd["event_type"],
                        config=rd["config"],
                    )
                )
            db.commit()
        return {"handlers": cleaned, "program_id": None}

    @staticmethod
    async def get_program_config(program_id: str) -> Optional[Dict[str, Any]]:
        """Get program-specific handler rows. Returns None if not set."""
        async with get_db_session() as db:
            rows = db.query(EventHandlerConfig).filter(EventHandlerConfig.program_id == program_id).all()
            if not rows:
                return None
            handlers = _rows_to_handlers(rows)
            return {"handlers": handlers, "program_id": program_id}

    @staticmethod
    async def get_program_config_by_name(program_name: str) -> Optional[Dict[str, Any]]:
        """Get program-specific handler config by program name."""
        from repository import ProgramRepository

        program = await ProgramRepository.get_program_by_name(program_name)
        if not program:
            return None
        return await EventHandlerConfigRepository.get_program_config(program["id"])

    @staticmethod
    async def get_program_addon_mode(program_id: str) -> bool:
        async with get_db_session() as db:
            p = db.query(Program).filter(Program.id == program_id).first()
            return bool(p and getattr(p, "event_handler_addon_mode", False))

    @staticmethod
    async def set_program_handler_addon_mode(program_id: str, addon_mode: bool) -> None:
        async with get_db_session() as db:
            p = db.query(Program).filter(Program.id == program_id).first()
            if p:
                p.event_handler_addon_mode = bool(addon_mode)
                db.commit()

    @staticmethod
    async def set_program_config(
        program_id: str, handlers: List[Dict[str, Any]], *, addon_mode: Optional[bool] = None
    ) -> Dict[str, Any]:
        """Replace all program handler rows. Optionally set ``event_handler_addon_mode``."""
        cleaned = EventHandlerConfigRepository.filter_handlers_for_program_persist(handlers)
        async with get_db_session() as db:
            db.query(EventHandlerConfig).filter(EventHandlerConfig.program_id == program_id).delete()
            for h in cleaned:
                if not h.get("id"):
                    continue
                rd = _handler_to_row(h)
                db.add(
                    EventHandlerConfig(
                        program_id=program_id,
                        handler_id=rd["handler_id"],
                        event_type=rd["event_type"],
                        config=rd["config"],
                    )
                )
            if addon_mode is not None:
                p = db.query(Program).filter(Program.id == program_id).first()
                if p:
                    p.event_handler_addon_mode = bool(addon_mode)
            db.commit()
        return {"handlers": cleaned, "program_id": program_id}

    @staticmethod
    async def delete_program_config(program_id: str) -> bool:
        """Remove program rows and reset addon mode."""
        async with get_db_session() as db:
            deleted = db.query(EventHandlerConfig).filter(EventHandlerConfig.program_id == program_id).delete()
            p = db.query(Program).filter(Program.id == program_id).first()
            if p:
                p.event_handler_addon_mode = False
            db.commit()
            return deleted > 0

    @staticmethod
    async def get_effective_config(program_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Fully merged handlers for the event-handler service.

        See module docstring for merge order and legacy behavior.
        """
        from services.notification_handler_templates import generate_handlers_from_notification_settings
        from repository import ProgramRepository

        system = get_system_handlers()
        system_ids = get_system_handler_ids()
        global_handlers = await EventHandlerConfigRepository.get_global_handlers()

        if not program_name:
            return _dedupe_handlers_keep_first(system + global_handlers)

        program = await ProgramRepository.get_program_by_name(program_name)
        if not program:
            return _dedupe_handlers_keep_first(system + global_handlers)

        notification_settings = program.get("notification_settings") or {}
        notify_handlers = generate_handlers_from_notification_settings(notification_settings)

        config = await EventHandlerConfigRepository.get_program_config(program["id"])
        if not config or not config.get("handlers"):
            return _dedupe_handlers_keep_first(system + global_handlers + notify_handlers)

        stored = EventHandlerConfigRepository._filter_discord_handlers(list(config["handlers"]))
        stored = [h for h in stored if not _is_notify_handler_id((h.get("id") or ""))]
        addon_mode = program.get("event_handler_addon_mode", False)

        if addon_mode:
            addons = [h for h in stored if (h.get("id") or "").strip() not in system_ids]
            return _dedupe_handlers_keep_first(system + global_handlers + addons + notify_handlers)

        legacy = [h for h in stored if (h.get("id") or "").strip() not in system_ids]
        return _dedupe_handlers_keep_first(system + legacy + notify_handlers)
