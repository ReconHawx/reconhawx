#!/usr/bin/env python3
import asyncio
import json
import os
import sys
from typing import Dict

from nats.aio.client import Client as NATS


EVENTS_STREAM = os.getenv("EVENTS_STREAM", "EVENTS")
SUBJECT = os.getenv("EVENT_SUBJECT", "events.assets.created.subdomain")
NATS_URL = os.getenv("NATS_URL", os.getenv("NATS_URL_DEV", "nats://nats:4222"))


async def main():
    nc = NATS()
    await nc.connect(NATS_URL)
    js = nc.jetstream()

    # Read JSON from stdin or default payload
    if not sys.stdin.isatty():
        payload = json.loads(sys.stdin.read())
    else:
        payload: Dict = {
            "event": "asset.created",
            "asset_type": "subdomain",
            "program_name": os.getenv("PROGRAM_NAME", "Acme"),
            "record_id": "test-id",
            "name": "api.example.com",
        }

    data = json.dumps(payload).encode()
    ack = await js.publish(SUBJECT, data)
    print(f"Published to {SUBJECT} seq={ack.seq}")
    await nc.drain()


if __name__ == "__main__":
    asyncio.run(main())


