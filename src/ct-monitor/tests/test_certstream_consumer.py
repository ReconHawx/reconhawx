"""Tests for CertStreamConsumer._process_certificate (no WebSocket)."""

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
