#!/usr/bin/env python3
import asyncio
import json
import logging
import traceback
from typing import Any, Awaitable, Callable, Optional

from nats.aio.client import Client as NATS
from nats.js.api import ConsumerConfig, DeliverPolicy, AckPolicy

from .config import NotifierConfig

logger = logging.getLogger(__name__)


class EventsSubscriber:
    def __init__(self, cfg: NotifierConfig):
        self.cfg = cfg
        self.nc: NATS | None = None
        self.js = None
        self.consumer_name = "notifier"
        self.subscription = None

    async def _process_one_message(
        self,
        msg: Any,
        handler: Callable[[str, dict], Awaitable[bool]],
        semaphore: Optional[asyncio.Semaphore],
    ) -> None:
        """Process a single message: decode, run handler, ack/nak. Optional semaphore limits concurrency."""
        subject = msg.subject
        payload: dict = {}
        try:
            payload = json.loads(msg.data.decode("utf-8")) if msg.data else {}
        except json.JSONDecodeError as e:
            logger.error("Failed to decode message payload: %s", e)
        except Exception as e:
            logger.error("Unexpected error decoding message: %s", e)

        ok = False
        try:
            if semaphore is not None:
                async with semaphore:
                    logger.debug("Received event: %s with payload: %s", subject, payload)
                    ok = await handler(subject, payload)
            else:
                logger.debug("Received event: %s with payload: %s", subject, payload)
                ok = await handler(subject, payload)
        except Exception as e:
            logger.error("Handler error for %s: %s", subject, e)
            logger.debug("Handler traceback: %s", traceback.format_exc())

        try:
            if ok:
                await msg.ack()
                logger.debug("Acknowledged message: %s", subject)
            else:
                await msg.nak()
                logger.warning("Negative acknowledgment for message: %s", subject)
        except Exception as e:
            logger.error("Error acknowledging message %s: %s", subject, e)

    async def connect(self):
        """Connect to NATS and set up the consumer"""
        try:
            self.nc = NATS()
            await self.nc.connect(
                self.cfg.nats_url, 
                connect_timeout=10,  # Increased timeout for better reliability
                reconnect_time_wait=1,
                max_reconnect_attempts=5
            )
            self.js = self.nc.jetstream()
            logger.info("Connected to NATS %s", self.cfg.nats_url)

            # Ensure consumer exists with optimized configuration for real-time processing
            consumer_cfg = ConsumerConfig(
                name=self.consumer_name,
                # Receive all available messages, including those published before consumer creation
                deliver_policy=DeliverPolicy.ALL,
                ack_policy=AckPolicy.EXPLICIT,
                filter_subject=self.cfg.nats_subject_pattern,
                durable_name=self.consumer_name,
                # Optimize for rapid event processing
                max_deliver=3,  # Allow 3 redelivery attempts
                ack_wait=30,   # 30 seconds to acknowledge
            )
            
            try:
                # Use existing durable consumer if present to preserve ACK sequence;
                # otherwise create it starting at NEW messages
                try:
                    existing_info = await self.js.consumer_info(self.cfg.nats_stream, self.consumer_name)
                    logger.info("Using existing consumer '%s' on stream '%s'", self.consumer_name, self.cfg.nats_stream)
                    logger.debug("Consumer info: pending=%s, delivered=%s", existing_info.num_pending, existing_info.delivered.stream_seq)
                except Exception:
                    await self.js.add_consumer(self.cfg.nats_stream, consumer_cfg)
                    logger.info("Created consumer '%s' on stream '%s' with NEW policy", self.consumer_name, self.cfg.nats_stream)
            except Exception as e:
                logger.warning("Consumer setup error: %s", e)

            self.subscription = await self.js.pull_subscribe(
                self.cfg.nats_subject_pattern, self.consumer_name
            )
            logger.info("Subscribed to %s on stream %s", self.cfg.nats_subject_pattern, self.cfg.nats_stream)
            
        except Exception as e:
            logger.error("Failed to connect to NATS: %s", e)
            raise

    async def run(self, handler: Callable[[str, dict], Awaitable[bool]]):
        """Run the event processing loop. Messages in each fetch batch are processed
        concurrently up to max_concurrent_messages (config); each message is ack/nak'd
        only after its handler completes."""
        if not self.subscription:
            raise RuntimeError("Subscriber not initialized")

        max_concurrent = self.cfg.max_concurrent_messages
        semaphore: Optional[asyncio.Semaphore] = (
            asyncio.Semaphore(max_concurrent) if max_concurrent > 0 else None
        )
        if semaphore is not None:
            logger.info("Starting event processing loop (max %s concurrent messages)...", max_concurrent)
        else:
            logger.info("Starting event processing loop (sequential)...")

        while True:
            try:
                msgs = await self.subscription.fetch(200, timeout=0.5)

                if not msgs:
                    continue

                logger.debug("Processing %s messages from NATS", len(msgs))

                if semaphore is None:
                    # Sequential: process one at a time (original behavior)
                    for msg in msgs:
                        await self._process_one_message(msg, handler, None)
                else:
                    # Concurrent: cap concurrency with semaphore, await all before next fetch
                    tasks = [
                        self._process_one_message(msg, handler, semaphore)
                        for msg in msgs
                    ]
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    for i, r in enumerate(results):
                        if isinstance(r, Exception):
                            logger.error(
                                "Task for message %s failed: %s",
                                getattr(msgs[i], "subject", i),
                                r,
                            )

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error("Error in event processing loop: %s", e)
                await asyncio.sleep(1)
                continue

    async def close(self):
        """Close the NATS connection gracefully"""
        try:
            if self.nc:
                logger.info("Closing NATS connection...")
                await self.nc.drain()
                logger.info("NATS connection drained successfully")
        except Exception as e:
            logger.warning("Error draining NATS connection: %s", e)
            try:
                if self.nc:
                    await self.nc.close()
                    logger.info("NATS connection closed")
            except Exception as close_error:
                logger.error("Error closing NATS connection: %s", close_error)


