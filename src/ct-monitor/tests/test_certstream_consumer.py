"""Tests for CertStreamConsumer._process_certificate (no WebSocket)."""

import asyncio

import pytest


@pytest.mark.asyncio
async def test_process_certificate_ignores_non_certificate_update():
    from certstream_consumer import CertStreamConsumer

    seen = []

    async def cb(c):
        seen.append(c)

    consumer = CertStreamConsumer(callback=cb, tld_filter={"com"})
    await consumer._process_certificate({"message_type": "heartbeat", "data": {}})
    assert seen == []


@pytest.mark.asyncio
async def test_process_certificate_wildcard_and_case():
    from certstream_consumer import CertStreamConsumer

    seen = []

    async def cb(c):
        seen.append(c)

    consumer = CertStreamConsumer(callback=cb, tld_filter=None)
    msg = {
        "message_type": "certificate_update",
        "data": {
            "leaf_cert": {
                "subject": {"CN": "*.Example.COM"},
                "all_domains": ["*.WILD.Example.COM"],
                "issuer": {"O": "TestCA", "CN": "TestCA CN"},
                "not_before": "nb",
                "not_after": "na",
                "fingerprint": "fp",
                "serial_number": "1",
            },
            "source": {"name": "src"},
            "cert_index": 0,
            "seen": "s",
            "update_type": "u",
        },
    }
    await consumer._process_certificate(msg)
    assert len(seen) == 1
    domains = set(seen[0].domains)
    # CN is stored lowercased only; SAN entries strip a leading "*." via lstrip("*.")
    assert "*.example.com" in domains
    assert "wild.example.com" in domains


@pytest.mark.asyncio
async def test_process_certificate_tld_filter():
    from certstream_consumer import CertStreamConsumer

    seen = []

    async def cb(c):
        seen.append(c)

    consumer = CertStreamConsumer(callback=cb, tld_filter={"com"})
    msg = {
        "message_type": "certificate_update",
        "data": {
            "leaf_cert": {
                "subject": {"CN": "x.io"},
                "all_domains": [],
                "issuer": {"O": "O", "CN": "CN"},
            },
            "source": {"name": "s"},
        },
    }
    await consumer._process_certificate(msg)
    assert seen == []
    assert consumer._stats.filtered_by_tld >= 1

    msg2 = {
        "message_type": "certificate_update",
        "data": {
            "leaf_cert": {
                "subject": {"CN": "ok.example.com"},
                "all_domains": [],
                "issuer": {"O": "O", "CN": "CN"},
            },
            "source": {"name": "s"},
        },
    }
    await consumer._process_certificate(msg2)
    assert len(seen) == 1
    assert "ok.example.com" in seen[0].domains


def test_message_passes_tld_filter():
    from certstream_consumer import message_passes_tld_filter

    io_msg = {
        "message_type": "certificate_update",
        "data": {"leaf_cert": {"subject": {"CN": "x.io"}, "all_domains": []}},
    }
    assert message_passes_tld_filter(io_msg, {"com"}) is False
    com_msg = {
        "message_type": "certificate_update",
        "data": {"leaf_cert": {"subject": {"CN": "ok.com"}, "all_domains": []}},
    }
    assert message_passes_tld_filter(com_msg, {"com"}) is True
    assert message_passes_tld_filter(io_msg, None) is True


@pytest.mark.asyncio
async def test_enqueue_skips_non_matching_tld_before_queue():
    from certstream_consumer import CertStreamConsumer

    async def cb(c):
        pass

    consumer = CertStreamConsumer(callback=cb, tld_filter={"com"}, queue_maxsize=10)
    consumer._running = True
    consumer._loop = asyncio.get_running_loop()
    consumer._queue = asyncio.Queue(maxsize=10)

    io_msg = {
        "message_type": "certificate_update",
        "data": {"leaf_cert": {"subject": {"CN": "x.io"}, "all_domains": []}},
    }
    consumer._enqueue_message(io_msg)
    assert consumer._queue.qsize() == 0
    assert consumer._stats.filtered_before_queue == 1

    com_msg = {
        "message_type": "certificate_update",
        "data": {"leaf_cert": {"subject": {"CN": "ok.com"}, "all_domains": []}},
    }
    consumer._enqueue_message(com_msg)
    assert consumer._queue.qsize() == 1


@pytest.mark.asyncio
async def test_enqueue_drops_when_queue_80_percent_full():
    from certstream_consumer import CertStreamConsumer

    async def cb(c):
        pass

    consumer = CertStreamConsumer(callback=cb, tld_filter={"com"}, queue_maxsize=10)
    consumer._running = True
    consumer._loop = asyncio.get_running_loop()
    consumer._queue = asyncio.Queue(maxsize=10)

    com_msg = {
        "message_type": "certificate_update",
        "data": {"leaf_cert": {"subject": {"CN": "a.com"}, "all_domains": []}},
    }
    for _ in range(8):
        consumer._enqueue_message(com_msg)
    assert consumer._queue.qsize() == 8

    consumer._enqueue_message(com_msg)
    assert consumer._stats.queue_drops >= 1


@pytest.mark.asyncio
async def test_worker_pool_respects_concurrency_and_keeps_backpressure():
    from certstream_consumer import CertStreamConsumer

    observed_peak = 0
    in_flight = 0
    done = 0
    gate = asyncio.Event()

    async def slow_cb(_cert):
        nonlocal in_flight, observed_peak, done
        in_flight += 1
        observed_peak = max(observed_peak, in_flight)
        await gate.wait()
        in_flight -= 1
        done += 1

    consumer = CertStreamConsumer(
        callback=slow_cb,
        tld_filter=None,
        queue_maxsize=50,
        match_concurrency=2,
    )
    consumer._running = True
    consumer._queue = asyncio.Queue(maxsize=50)

    msg = {
        "message_type": "certificate_update",
        "data": {
            "leaf_cert": {
                "subject": {"CN": "a.example.com"},
                "all_domains": [],
                "issuer": {"O": "O", "CN": "CN"},
            },
            "source": {"name": "s"},
        },
    }
    for _ in range(4):
        consumer._queue.put_nowait(msg)

    processor = asyncio.create_task(consumer._process_queue())
    for _ in range(200):
        if in_flight >= 2:
            break
        await asyncio.sleep(0.01)
    await asyncio.sleep(0.05)
    assert observed_peak == 2
    assert consumer.get_match_in_flight() == 2
    # Unprocessed messages stay queued (real backpressure), not in pending tasks.
    assert consumer._queue.qsize() == 2

    gate.set()
    for _ in range(200):
        if done == 4:
            break
        await asyncio.sleep(0.01)
    assert done == 4

    consumer._running = False
    processor.cancel()
    await asyncio.gather(processor, return_exceptions=True)
