#!/usr/bin/env python3
"""
Handler config structures for the event-handler service.

Handler definitions are loaded from the API; this module builds in-memory
`HandlerSet` / `SimpleHandlerRegistry` instances from config dicts.
"""

import logging
from typing import Dict, Any, List, Optional

from .event_handlers import (
    SimpleEventHandler,
    SimpleHandlerRegistry,
    SimpleBatchManager,
    ActionResult,
    _normalize_handler_event_types,
)

logger = logging.getLogger(__name__)


def create_handlers_from_config(handlers_config: List[Dict[str, Any]], registry: SimpleHandlerRegistry) -> None:
    """Create and register handlers from a config list into the given registry."""
    for handler_config in handlers_config:
        try:
            event_types = _normalize_handler_event_types(handler_config.get("event_type"))
            if not event_types:
                continue
            handler_id = handler_config.get("id", event_types[0].replace(".", "_"))
            if not handler_config.get("actions"):
                logger.warning(f"Handler '{handler_id}' has no actions, skipping")
                continue
            handler = SimpleEventHandler(handler_id, handler_config)
            declared = set(handler.event_types)
            for per_type_key in handler.conditions_by_event_type:
                if per_type_key not in declared:
                    logger.warning(
                        "Handler '%s' has conditions_by_event_type key '%s' not in event_type list %s",
                        handler_id,
                        per_type_key,
                        sorted(declared),
                    )
            registry.register_handler(handler)
        except Exception as e:
            logger.error(f"Failed to create handler: {e}")


class HandlerSet:
    """Handler set for a specific program - holds handlers and delegates to registry."""

    def __init__(self, handlers_config: List[Dict[str, Any]], batch_manager: Optional[SimpleBatchManager] = None):
        self.registry = SimpleHandlerRegistry()
        create_handlers_from_config(handlers_config, self.registry)
        if batch_manager:
            self.registry.set_batch_manager(batch_manager)

    async def handle_event(self, event_type: str, event_data: Dict[str, Any]) -> List[ActionResult]:
        """Handle an event with this set's handlers."""
        return await self.registry.handle_event(event_type, event_data)

    async def process_expired_batches(self) -> int:
        """Process expired batches for this set's handlers."""
        return await self.registry.process_expired_batches()

    def get_handler_by_id(self, handler_id: str):
        """Get handler by id (for batch recovery)."""
        return self.registry.get_handler_by_id(handler_id)
