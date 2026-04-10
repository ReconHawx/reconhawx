#!/usr/bin/env python3
"""
Simplified Notifier Application

This replaces the complex main.py with a much cleaner, more maintainable approach.
Loads handler definitions from the API (per-program).
"""

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any, Dict, List

if TYPE_CHECKING:
    from .event_handlers import SimpleEventHandler

import redis
import uvicorn

from .config import NotifierConfig
from .http_api import create_http_app
from .nats_client import EventsSubscriber
from .program_settings import ProgramSettingsProvider
from .event_handlers import ActionResult, SimpleBatchManager, close_http_client
from .routing import normalize_event_data, should_skip_event
from .handler_config import HandlerSet
from .api_config_provider import ApiConfigProvider

logger = logging.getLogger(__name__)


def setup_logging(level: str):
    """Setup logging configuration"""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )


class SimpleNotifierApp:
    """Simplified Notifier Application"""
    
    def __init__(self):
        self.cfg = NotifierConfig()
        setup_logging(self.cfg.log_level)
        
        # Core components
        self.redis = redis.from_url(self.cfg.redis_url)
        self.subscriber = EventsSubscriber(self.cfg)
        self.settings_provider = ProgramSettingsProvider(self.cfg, self.redis)
        
        # Initialize simplified handler system (handler definitions from API only)
        if self.cfg.enable_event_handlers:
            self.batch_manager = SimpleBatchManager(self.redis, self.cfg)
            self.api_config_provider = ApiConfigProvider(self.cfg, self.redis)
            self._handler_set_cache: Dict[str, tuple] = {}  # program_name -> (HandlerSet, expiry_ts)
            logger.info("Event handler system initialized (API config, per-program)")
        else:
            self.batch_manager = None
            self.api_config_provider = None
            self._handler_set_cache = {}
            logger.info("Event handler system disabled")

        self._uvicorn_server: uvicorn.Server | None = None
        self._processing_paused = False
        self._pause_lock = asyncio.Lock()

    def is_processing_paused(self) -> bool:
        return self._processing_paused

    async def pause_processing(self) -> None:
        async with self._pause_lock:
            self._processing_paused = True
            logger.info("Event processing paused (NATS fetch and batch recovery idle)")

    async def resume_processing(self) -> None:
        async with self._pause_lock:
            self._processing_paused = False
            logger.info("Event processing resumed")

    async def start(self):
        """Start the notifier application"""
        logger.info("Starting simplified notifier application")
        
        await self.subscriber.connect()
        
        # Start background tasks
        if self.batch_manager:
            asyncio.create_task(self._batch_recovery_loop())

        http_app = create_http_app(self)
        uvicorn_config = uvicorn.Config(
            http_app,
            host=self.cfg.http_host,
            port=self.cfg.http_port,
            log_level=self.cfg.log_level.lower(),
            access_log=False,
        )
        self._uvicorn_server = uvicorn.Server(uvicorn_config)
        http_task = asyncio.create_task(self._uvicorn_server.serve())
        logger.info(
            "HTTP API listening on %s:%s (GET /status, POST /control/pause|resume|flush-batches|clear-batches)",
            self.cfg.http_host,
            self.cfg.http_port,
        )

        try:
            await self.subscriber.run(
                self.handle_event, is_paused=self.is_processing_paused
            )
        finally:
            if self._uvicorn_server is not None:
                self._uvicorn_server.should_exit = True
            await http_task
            self._uvicorn_server = None
    
    async def handle_event(self, subject: str, payload: Dict[str, Any]) -> bool:
        """
        Main event handler - much simpler than the original
        
        Returns True if event was processed successfully
        """
        try:
            logger.debug(f"Received event: {subject}")
            
            # Check if this is a batch event from the API
            if payload.get('event') == 'batch':
                return await self._handle_batch_event(subject, payload)
            else:
                return await self._handle_single_event(subject, payload)
                
        except Exception as e:
            logger.error(f"Error handling event {subject}: {e}")
            return False
    
    async def _handle_batch_event(self, subject: str, payload: Dict[str, Any]) -> bool:
        """Handle batch events from the API"""
        try:
            events = payload.get('events', [])
            if not events:
                logger.warning(f"Empty batch event received: {subject}")
                return True
            
            logger.info(f"Processing batch event with {len(events)} individual events")
            
            processed = 0
            for event_data in events:
                try:
                    event_subject = event_data.get('subject', 'events.unknown')
                    event_payload = event_data.get('payload', {})
                    
                    success = await self._handle_single_event(event_subject, event_payload)
                    if success:
                        processed += 1
                except Exception as e:
                    logger.error(f"Error processing event in batch: {e}")
                    continue
            
            logger.info(f"Processed {processed}/{len(events)} events from batch")
            return True
            
        except Exception as e:
            logger.error(f"Error handling batch event {subject}: {e}")
            return False
    
    async def _handle_single_event(self, subject: str, payload: Dict[str, Any]) -> bool:
        """Handle a single event"""
        try:
            # Normalize event data
            event_data = normalize_event_data(subject, payload)
            
            # Add API configuration
            event_data['api_base_url'] = self.cfg.api_url
            event_data['internal_api_key'] = self.cfg.internal_service_api_key
            
            # Debug logging for typosquat events
            if event_data.get('event_type') == 'findings.typosquat.created':
                logger.info(f"Processing typosquat event: {event_data.get('name')} (program: {event_data.get('program_name')})")
            
            # Skip if event should be ignored
            if should_skip_event(event_data):
                return True
            
            # Add program settings if any handlers need them
            program_name = event_data['program_name']
            if self._handlers_need_program_settings(event_data['event_type']):
                program_settings = self.settings_provider.get_program_settings(program_name)
                event_data['program_settings'] = program_settings or {}
            else:
                event_data['program_settings'] = {}
            
            # Process with handlers
            if self.cfg.enable_event_handlers:
                handler_set = self._get_handler_set(program_name)
                results = await handler_set.handle_event(event_data['event_type'], event_data)

                # Log results
                successful = [r for r in results if r.success]
                if successful:
                    logger.debug(f"Event processed successfully: {len(successful)}/{len(results)} actions succeeded")
                    return True
                elif results:
                    logger.warning(f"Event processing failed: 0/{len(results)} actions succeeded")
                    return False
                else:
                    logger.debug(f"No handlers matched for event type: {event_data['event_type']}")
                    return True

            return True
            
        except Exception as e:
            logger.error(f"Error processing single event {subject}: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False
    
    def _get_handler_set(self, program_name: str) -> HandlerSet:
        """Get or create HandlerSet for program (cached with TTL)."""
        now = time.time()
        cache_ttl = self.cfg.api_config_cache_ttl
        cached = self._handler_set_cache.get(program_name)
        if cached:
            handler_set, expiry = cached
            if now < expiry:
                return handler_set
        handlers = self.api_config_provider.get_handlers(program_name)
        handler_set = HandlerSet(handlers, self.batch_manager)
        self._handler_set_cache[program_name] = (handler_set, now + cache_ttl)
        return handler_set

    def _handlers_need_program_settings(self, event_type: str) -> bool:
        """Assume handlers may need program settings (templates often reference notify/discord keys)."""
        return True
    
    async def _batch_recovery_loop(self):
        """Background task to process expired batches"""
        logger.info("Starting batch recovery loop (checks every 15 seconds)")

        while True:
            try:
                if self.is_processing_paused():
                    await asyncio.sleep(15)
                    continue
                processed = await self._process_expired_batches_api_mode()
                if processed > 0:
                    logger.info(f"Processed {processed} expired batches")

                await asyncio.sleep(15)

            except Exception as e:
                logger.error(f"Error in batch recovery loop: {e}")
                import traceback
                logger.error(f"Traceback: {traceback.format_exc()}")
                await asyncio.sleep(30)

    async def _deliver_batched_events(
        self,
        handler: "SimpleEventHandler",
        program_name: str,
        batch_age: int,
        batched_events: List[Dict[str, Any]],
    ) -> List[ActionResult]:
        """Run batch actions for events already removed from Redis."""
        first_event = batched_events[0] if batched_events else {}
        program_settings = self.settings_provider.get_program_settings(program_name)
        trigger_event = {
            "program_name": program_name,
            "expired_batch": True,
            "batch_age": batch_age,
            "event_type": handler.event_type,
            "event_family": handler.event_type,
            "api_base_url": first_event.get("api_base_url", "http://api:8000"),
            "internal_api_key": first_event.get("internal_api_key", ""),
            **first_event,
        }
        trigger_event["program_settings"] = program_settings or {}
        return await handler._execute_batch_actions(batched_events, trigger_event)

    async def _process_expired_batches_api_mode(self) -> int:
        """Process expired batches when using API config (per-program handler sets)."""
        if not self.batch_manager:
            return 0
        processed = 0
        expired_batches = self.batch_manager.get_expired_batches()
        for handler_id, program_name, age in expired_batches:
            try:
                handler_set = self._get_handler_set(program_name)
                handler = handler_set.get_handler_by_id(handler_id)
                if not handler:
                    logger.warning(f"Handler not found for expired batch: {handler_id}")
                    continue
                batched_events = self.batch_manager.get_and_clear_batch(handler_id, program_name)
                if not batched_events:
                    continue
                logger.info(
                    f"Processing expired batch: {handler_id}:{program_name} with {len(batched_events)} events (age: {age}s)"
                )
                results = await self._deliver_batched_events(handler, program_name, age, batched_events)
                successful = [r for r in results if r.success]
                logger.info(
                    f"Processed expired batch {handler_id}:{program_name} - {len(batched_events)} events, {len(successful)}/{len(results)} successful actions"
                )
                processed += 1
            except Exception as e:
                logger.error(f"Error processing expired batch {handler_id}:{program_name}: {e}")
                import traceback
                logger.error(traceback.format_exc())
        return processed

    async def flush_pending_batches(self) -> Dict[str, Any]:
        """Process all Redis-backed batches that have items (admin flush), regardless of age."""
        if not self.batch_manager:
            return {
                "status": "skipped",
                "reason": "event handlers / batch manager disabled",
                "flushed": 0,
                "orphans_cleared": 0,
                "errors": [],
                "pending_seen": 0,
            }

        pending = self.batch_manager.list_pending_batches_with_items()
        flushed = 0
        orphans_cleared = 0
        errors: List[Dict[str, Any]] = []

        for handler_id, program_name, age in pending:
            try:
                handler_set = self._get_handler_set(program_name)
                handler = handler_set.get_handler_by_id(handler_id)
                batched_events = self.batch_manager.get_and_clear_batch(handler_id, program_name)
                if not batched_events:
                    continue
                if not handler:
                    logger.warning(
                        "Flush: handler %s not found for program %s; discarding %s batched events",
                        handler_id,
                        program_name,
                        len(batched_events),
                    )
                    orphans_cleared += 1
                    errors.append(
                        {
                            "handler_id": handler_id,
                            "program_name": program_name,
                            "error": "handler not found; batch discarded",
                        }
                    )
                    continue
                logger.info(
                    "Flush batch %s:%s with %s events (age %ss)",
                    handler_id,
                    program_name,
                    len(batched_events),
                    age,
                )
                results = await self._deliver_batched_events(
                    handler, program_name, age, batched_events
                )
                successful = [r for r in results if r.success]
                logger.info(
                    "Flushed batch %s:%s — %s/%s actions succeeded",
                    handler_id,
                    program_name,
                    len(successful),
                    len(results),
                )
                flushed += 1
            except Exception as e:
                logger.error(
                    "Error flushing batch %s:%s: %s", handler_id, program_name, e
                )
                import traceback

                logger.error(traceback.format_exc())
                errors.append(
                    {
                        "handler_id": handler_id,
                        "program_name": program_name,
                        "error": str(e),
                    }
                )

        return {
            "status": "ok",
            "flushed": flushed,
            "orphans_cleared": orphans_cleared,
            "errors": errors,
            "pending_seen": len(pending),
        }

    async def clear_pending_batches(self) -> Dict[str, Any]:
        """Delete all Redis-backed batch queues without executing actions."""
        if not self.batch_manager:
            return {
                "status": "skipped",
                "reason": "event handlers / batch manager disabled",
                "batches_cleared": 0,
                "events_discarded": 0,
                "errors": [],
            }
        return await asyncio.to_thread(self.batch_manager.delete_all_pending_batches)

    async def shutdown(self):
        """Graceful shutdown"""
        logger.info("Shutting down notifier application")
        if self._uvicorn_server is not None:
            self._uvicorn_server.should_exit = True
        try:
            await close_http_client()
        except Exception as e:
            logger.error(f"Error closing HTTP client: {e}")
        try:
            await self.subscriber.close()
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")


async def main():
    """Main entry point"""
    app = SimpleNotifierApp()
    try:
        await app.start()
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise
    finally:
        await app.shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass