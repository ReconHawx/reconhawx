#!/usr/bin/env python3
import asyncio
import json
import logging
import os
import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

from nats.aio.client import Client as NATS
from nats.js.api import StreamConfig, RetentionPolicy

logger = logging.getLogger(__name__)

@dataclass
class EventBatch:
    """Represents a batch of events to be published"""
    events: List[Dict[str, Any]]
    created_at: float
    max_age: float = 5.0  # Max age in seconds before forcing publish

class RobustEventPublisher:
    """
    Robust NATS publisher with persistent connection, batching, and graceful degradation.
    
    Features:
    - Single persistent NATS connection
    - Event batching for high-volume scenarios
    - Connection health monitoring
    - Exponential backoff retry logic
    - Graceful fallback to logging when NATS unavailable
    - Background batch processing
    """
    
    def __init__(self):
        self.nats_url = os.getenv("NATS_URL", "nats://nats:4222")
        self.stream = os.getenv("EVENTS_STREAM", "EVENTS")
        # Store loop lazily to avoid issues during module import
        self.loop = None
        
        # Connection management
        self._nc: Optional[NATS] = None
        self._connected = False
        self._connection_lock = asyncio.Lock()
        self._last_connection_attempt = 0
        self._connection_retry_delay = 1.0  # Start with 1 second
        
        # Batching configuration
        self.batch_size = int(os.getenv("EVENT_BATCH_SIZE", "50"))
        self.batch_timeout = float(os.getenv("EVENT_BATCH_TIMEOUT", "2.0"))
        self._event_queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._current_batch: Optional[EventBatch] = None
        self._batch_lock = asyncio.Lock()
        
        # Background processing - initialize lazily
        self._batch_processor_task: Optional[asyncio.Task] = None
        self._batch_processor_started = False
    
    def _start_batch_processor(self):
        """Start the background batch processing task"""
        # Only start if not already started and we have a running loop
        if self._batch_processor_started:
            return
            
        try:
            # Check if we're in an async context
            asyncio.get_running_loop()
            if not self._batch_processor_task or self._batch_processor_task.done():
                self._batch_processor_task = asyncio.create_task(self._process_batches())
                self._batch_processor_started = True
                logger.info("Event batch processor started")
        except RuntimeError:
            # No running loop, will start when first event is published
            logger.debug("No running event loop, batch processor will start when needed")
    
    async def _ensure_batch_processor(self):
        """Ensure the batch processor is running"""
        if not self._batch_processor_started:
            try:
                # Get current loop if we don't have one stored
                if not self.loop:
                    try:
                        self.loop = asyncio.get_running_loop()
                    except RuntimeError:
                        logger.warning("No running event loop available")
                        return
                
                # Try to start the processor
                self._start_batch_processor()
            except Exception as e:
                logger.error(f"Failed to start batch processor: {e}")
    
    async def _ensure_stream(self) -> bool:
        """Ensure JetStream stream exists"""
        try:
            if not self._nc:
                return False
                
            js = self._nc.jetstream()
            
            # Try to get stream info
            try:
                await js.stream_info(self.stream)
                logger.debug(f"Stream {self.stream} already exists")
                return True
            except Exception:
                # Stream doesn't exist, create it
                logger.info(f"Creating JetStream stream {self.stream}")
                
                stream_config = StreamConfig(
                    name=self.stream,
                    subjects=["events.>"],  # Match all events.* subjects
                    retention=RetentionPolicy.WORK_QUEUE,
                    max_age=86400,  # 24 hours
                    max_msgs=1000000,  # 1M messages
                    max_bytes=1024*1024*1024,  # 1GB
                )
                
                await js.add_stream(stream_config)
                logger.info(f"Successfully created stream {self.stream}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to ensure stream {self.stream}: {e}")
            return False

    async def _ensure_connection(self) -> bool:
        """Ensure NATS connection is established with retry logic"""
        if self._connected and self._nc and not self._nc.is_closed:
            return True
        
        async with self._connection_lock:
            # Check again after acquiring lock
            if self._connected and self._nc and not self._nc.is_closed:
                return True
            
            # Implement exponential backoff
            current_time = time.time()
            if current_time - self._last_connection_attempt < self._connection_retry_delay:
                return False
            
            self._last_connection_attempt = current_time
            
            try:
                # Close existing connection if any
                if self._nc:
                    try:
                        await self._nc.close()
                    except Exception:
                        pass
                
                # Create new connection
                self._nc = NATS()
                await self._nc.connect(
                    self.nats_url,
                    connect_timeout=10,  # Increased from 2s
                    reconnect_time_wait=1.0,
                    max_reconnect_attempts=5,
                    ping_interval=20,
                    max_outstanding_pings=5
                )
                
                self._connected = True
                self._connection_retry_delay = 1.0  # Reset retry delay on success
                logger.info("NATS connection established successfully")
                
                # Ensure JetStream stream exists
                if not await self._ensure_stream():
                    logger.warning("Failed to ensure JetStream stream exists")
                    # Don't fail connection for this, but log it
                
                return True
                
            except Exception as e:
                self._connected = False
                # Exponential backoff with max cap
                self._connection_retry_delay = min(self._connection_retry_delay * 2, 60.0)
                logger.warning(f"Failed to connect to NATS: {e}. Retrying in {self._connection_retry_delay}s")
                return False
    
    async def _publish_single_event(self, subject: str, payload: Dict[str, Any]) -> bool:
        """Publish a single event with retry logic"""
        if not await self._ensure_connection():
            return False
        
        max_retries = 3
        retry_delay = 0.1
        
        for attempt in range(max_retries):
            try:
                js = self._nc.jetstream()
                data = json.dumps(payload).encode("utf-8")
                # Publish and get acknowledgment like in the working debug script
                ack = await js.publish(subject, data, timeout=10)
                logger.debug(f"Successfully published event to {subject}, ACK: {ack}")
                return True
                
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Event publish attempt {attempt + 1} failed for {subject}: {e}. Retrying...")
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                    
                    # Try to reconnect if connection lost or stream missing
                    if "connection" in str(e).lower() or "timeout" in str(e).lower():
                        self._connected = False
                        await self._ensure_connection()
                    elif "no response from stream" in str(e).lower():
                        logger.info("Stream missing, attempting to create it")
                        await self._ensure_stream()
                else:
                    logger.error(f"Event publish failed for {subject} after {max_retries} attempts: {e}")
                    return False
        
        return False
    
    async def _process_batches(self):
        """Background task that processes event batches"""
        while True:
            try:
                # Wait for events or timeout to check for aged batches
                try:
                    await asyncio.wait_for(self._event_queue.get(), timeout=self.batch_timeout)
                except asyncio.TimeoutError:
                    # Timeout occurred, check if we have an aged batch to publish
                    async with self._batch_lock:
                        if self._current_batch:
                            current_time = time.time()
                            batch_age = current_time - self._current_batch.created_at
                            if batch_age >= self.batch_timeout and len(self._current_batch.events) > 0:
                                logger.debug(f"Publishing aged batch: {len(self._current_batch.events)} events, age: {batch_age:.2f}s")
                                await self._publish_batch(self._current_batch)
                                self._current_batch = None
                    continue
                
                # An event was queued, but we don't need to do anything special
                # The publish() method handles immediate publishing when batch is full
                # This processor only handles timeout-based publishing
                
            except Exception as e:
                logger.error(f"Error in batch processor: {e}")
                await asyncio.sleep(1)
    
    async def _publish_batch(self, batch: EventBatch):
        """Publish a batch of events"""
        if not batch.events:
            return
        
        try:
            # Group events by subject for efficiency
            events_by_subject: Dict[str, List[Dict[str, Any]]] = {}
            for event in batch.events:
                subject = event.get('subject', 'events.unknown')
                if subject not in events_by_subject:
                    events_by_subject[subject] = []
                events_by_subject[subject].append(event)
            
            # Publish each subject group as a batch (even if only 1 event)
            for subject, events in events_by_subject.items():
                # Always publish as batch format for consistency
                batch_payload = {
                    "event": "batch",
                    "count": len(events),
                    "events": events,
                    "batch_id": f"batch_{int(time.time())}_{hash(subject)}"
                }
                
                # Publish to original subject - event-handler will handle batching
                await self._publish_single_event(subject, batch_payload)
            
            #logger.info(f"Published batch of {len(batch.events)} events")
            
        except Exception as e:
            logger.error(f"Error publishing batch: {e}")
            # Fallback: try to publish events individually
            for event in batch.events:
                try:
                    subject = event.get('subject', 'events.unknown')
                    await self._publish_single_event(subject, event)
                except Exception as individual_error:
                    logger.error(f"Failed to publish individual event: {individual_error}")
    
    async def publish(self, subject: str, payload: Dict[str, Any]):
        """
        Publish an event. Events are batched for efficiency.
        
        Args:
            subject: NATS subject for the event
            payload: Event data payload
        """
        try:
            # Ensure batch processor is running
            await self._ensure_batch_processor()
            
            # Add subject to payload for batching
            event_data = {
                "subject": subject,
                "payload": payload,
                "timestamp": time.time()
            }
            
            # Simple batching logic without race conditions
            async with self._batch_lock:
                # Create new batch if none exists
                if not self._current_batch:
                    self._current_batch = EventBatch(
                        events=[event_data],
                        created_at=time.time()
                    )
                    #logger.debug("Created new batch with 1 event")
                else:
                    # Add to existing batch
                    self._current_batch.events.append(event_data)
                    #logger.debug(f"Added event to batch, current size: {len(self._current_batch.events)}")
                    
                    # Check if batch should be published immediately
                    if len(self._current_batch.events) >= self.batch_size:
                        #logger.debug(f"Publishing full batch with {len(self._current_batch.events)} events")
                        await self._publish_batch(self._current_batch)
                        self._current_batch = None
            
            # Signal the batch processor that there's work to do
            try:
                self._event_queue.put_nowait(True)
            except asyncio.QueueFull:
                # Queue is full, but that's okay - the processor will handle it
                pass
                    
        except Exception as e:
            logger.error(f"Error queuing event for {subject}: {e}")
            # Fallback: try immediate publish
            try:
                await self._publish_single_event(subject, payload)
            except Exception as fallback_error:
                logger.error(f"Fallback publish also failed for {subject}: {fallback_error}")
    
    async def publish_immediate(self, subject: str, payload: Dict[str, Any]) -> bool:
        """
        Publish an event immediately without batching.
        Useful for critical events that shouldn't be delayed.
        
        Returns:
            bool: True if published successfully, False otherwise
        """
        return await self._publish_single_event(subject, payload)
    
    async def flush_batches(self):
        """Force publish all pending batches"""
        async with self._batch_lock:
            if self._current_batch:
                logger.info(f"Force flushing batch with {len(self._current_batch.events)} events")
                await self._publish_batch(self._current_batch)
                self._current_batch = None
    
    def get_batch_status(self) -> Dict[str, Any]:
        """Get current batch status for debugging"""
        if not self._current_batch:
            return {"status": "no_batch", "events": 0}
        
        current_time = time.time()
        batch_age = current_time - self._current_batch.created_at
        
        return {
            "status": "active",
            "events": len(self._current_batch.events),
            "age_seconds": batch_age,
            "batch_timeout": self.batch_timeout,
            "batch_size": self.batch_size,
            "will_publish_on_timeout": batch_age >= self.batch_timeout,
            "will_publish_on_size": len(self._current_batch.events) >= self.batch_size
        }
    
    async def start_batch_processor(self):
        """Manually start the batch processor if needed"""
        await self._ensure_batch_processor()
    
    async def shutdown(self):
        """Shutdown the publisher gracefully"""
        # Stop batch processor
        if self._batch_processor_task and not self._batch_processor_task.done():
            self._batch_processor_task.cancel()
            try:
                await self._batch_processor_task
            except asyncio.CancelledError:
                pass
        
        # Flush remaining batches
        await self.flush_batches()
        
        # Close NATS connection
        if self._nc:
            try:
                await self._nc.close()
            except Exception:
                pass
        
        logger.info("Event publisher shutdown complete")

# Global instance
publisher = RobustEventPublisher()

# Legacy compatibility - maintain the old interface
class EventPublisher:
    """Legacy compatibility wrapper"""
    
    def __init__(self):
        self.publisher = publisher
    
    def publish(self, subject: str, payload: Dict[str, Any]):
        """Legacy publish method - delegates to new publisher"""
        try:
            # Try to create task in current loop
            asyncio.create_task(self.publisher.publish(subject, payload))
        except RuntimeError:
            # If no running loop, use the stored loop
            if self.publisher.loop and not self.publisher.loop.is_closed():
                self.publisher.loop.create_task(self.publisher.publish(subject, payload))
            else:
                # Last resort: log error and try to publish immediately
                logger.error("No event loop available for publishing event")
                # Note: This will fail since we can't await in sync context
                # The user should use the async publisher directly in async contexts

# Create legacy instance for backward compatibility
legacy_publisher = EventPublisher()


