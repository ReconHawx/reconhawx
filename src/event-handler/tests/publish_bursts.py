#!/usr/bin/env python3
import asyncio
import json
import os
import random
import string
import argparse

from nats.aio.client import Client as NATS


async def publish_burst(nc: NATS, subject: str, count: int, program: str, kind: str, severity: str | None):
    js = nc.jetstream()
    for i in range(count):
        if kind == "subdomain":
            name = f"{random.choice(['api','app','cdn','edge','auth'])}-{i}.{random.choice(['example.com','acme.com'])}"
            payload = {
                "event": "asset.created",
                "asset_type": "subdomain",
                "program_name": program,
                "record_id": f"sd-{i}",
                "name": name,
            }
            subj = subject or "events.assets.created.subdomain"
        elif kind == "nuclei":
            sev = severity or random.choice(["medium", "high", "critical"]) 
            tid = "CVE-{}-{}".format(random.randint(2018, 2024), random.randint(1000, 9999))
            payload = {
                "event": "finding.created",
                "type": "nuclei",
                "severity": sev,
                "program_name": program,
                "record_id": f"nf-{i}",
                "template_id": tid,
                "url": f"https://{random.choice(['app','api'])}.{random.choice(['example.com','acme.com'])}/path",
            }
            subj = subject or "events.findings.created.nuclei"
        else:
            raise ValueError("Unsupported kind")

        await js.publish(subj, json.dumps(payload).encode())


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--kind", choices=["subdomain", "nuclei"], default="subdomain")
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--program", default="Acme")
    parser.add_argument("--severity")
    parser.add_argument("--subject")
    args = parser.parse_args()

    nats_url = os.getenv("NATS_URL", os.getenv("NATS_URL_DEV", "nats://nats:4222"))
    nc = NATS()
    await nc.connect(nats_url)

    await publish_burst(nc, args.subject, args.count, args.program, args.kind, args.severity)
    print("Published burst")
    await nc.drain()


if __name__ == "__main__":
    asyncio.run(main())


