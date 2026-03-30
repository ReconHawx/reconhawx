#!/usr/bin/env python3
"""
Test script to manually trigger a workflow via event handler system
"""

import asyncio
import json
import os
import sys
from typing import Dict

from nats.aio.client import Client as NATS


EVENTS_STREAM = os.getenv("EVENTS_STREAM", "EVENTS")
SUBJECT = "events.test.workflow.trigger"  # This will be parsed to event type "test.workflow.trigger"
NATS_URL = os.getenv("NATS_URL", os.getenv("NATS_URL_DEV", "nats://nats:4222"))


async def main():
    nc = NATS()
    await nc.connect(NATS_URL)
    js = nc.jetstream()

    # Create test event payload
    payload: Dict = {
        "program_name": os.getenv("PROGRAM_NAME", "h3xit"),
        "event_type": "test.workflow.trigger",
        "description": "Manual test event to trigger workflow",
        "test_data": {
            "triggered_by": "manual_test",
            "timestamp": "2024-01-01T00:00:00Z"
        }
    }

    # Allow custom payload from stdin
    if not sys.stdin.isatty():
        custom_payload = json.loads(sys.stdin.read())
        payload.update(custom_payload)

    print(f"Publishing test event to trigger workflow...")
    print(f"Subject: {SUBJECT}")
    print(f"Payload: {json.dumps(payload, indent=2)}")

    data = json.dumps(payload).encode()
    ack = await js.publish(SUBJECT, data)
    print(f"✅ Published to {SUBJECT} seq={ack.seq}")

    await nc.drain()


if __name__ == "__main__":
    asyncio.run(main())
