"""Tests for ``services.fireprox`` pure helpers and the TokenBucket.

boto3 / AWS-Gateway methods are patched out; we exercise the rate-limiter,
swagger-template builder, and in-memory proxy bookkeeping.
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def _patch_boto(monkeypatch) -> None:
    import services.fireprox as fp

    monkeypatch.setattr(fp.boto3, "client", lambda *a, **k: MagicMock())


def _make_service(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIA_TEST")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret")
    from services.fireprox import FireProxService

    return FireProxService(aws_region="us-east-1", rate_limit=100.0, burst_size=5)


def test_token_bucket_consumes_and_refills() -> None:
    from services.fireprox import TokenBucket

    bucket = TokenBucket(rate=1000.0, capacity=3)
    assert bucket.consume(1, block=False) is True
    assert bucket.consume(2, block=False) is True
    assert bucket.consume(1, block=False) is False
    time.sleep(0.02)
    assert bucket.consume(1, block=False) is True


def test_token_bucket_timeout_returns_false() -> None:
    from services.fireprox import TokenBucket

    bucket = TokenBucket(rate=0.1, capacity=1)
    assert bucket.consume(1, block=False) is True
    start = time.time()
    assert bucket.consume(1, block=True, timeout=0.2) is False
    assert time.time() - start < 1.0


def test_fireprox_service_defaults_region(monkeypatch) -> None:
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "k")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "s")
    from services.fireprox import FireProxService

    svc = FireProxService()
    assert svc.aws_region == "ca-central-1"
    assert svc._proxies == {}


def test_get_swagger_template_embeds_target_url(monkeypatch) -> None:
    svc = _make_service(monkeypatch)
    import services.fireprox as fp

    monkeypatch.setattr(
        fp.tldextract, "extract", lambda url: MagicMock(domain="example")
    )
    raw = svc._get_swagger_template("https://api.example.com/")
    doc = json.loads(raw.decode())
    assert doc["swagger"] == "2.0"
    root_uri = doc["paths"]["/"]["get"]["x-amazon-apigateway-integration"]["uri"]
    proxy_uri = doc["paths"]["/{proxy+}"]["x-amazon-apigateway-any-method"][
        "x-amazon-apigateway-integration"
    ]["uri"]
    assert root_uri == "https://api.example.com/"
    assert proxy_uri == "https://api.example.com/{proxy}"


def test_proxy_mapping_to_dict() -> None:
    from services.fireprox import ProxyMapping

    m = ProxyMapping(
        original_url="https://a.com",
        proxy_url="https://proxy.aws/",
        proxy_id="abc",
        region="us-east-1",
        created_at=datetime(2024, 1, 2, 3, 4, 5),
    )
    d = m.to_dict()
    assert d["proxy_id"] == "abc"
    assert d["created_at"] == "2024-01-02T03:04:05"


def test_create_proxy_returns_existing_without_api_call(monkeypatch) -> None:
    from services.fireprox import ProxyMapping

    svc = _make_service(monkeypatch)
    existing = ProxyMapping(
        original_url="https://a.com",
        proxy_url="https://proxy.aws/",
        proxy_id="abc",
        region=svc.aws_region,
        created_at=datetime.utcnow(),
    )
    svc._proxies["https://a.com"] = existing
    svc.client.create_rest_api = MagicMock(side_effect=AssertionError("should not be called"))
    result = svc.create_proxy("https://a.com")
    assert result is existing


def test_list_proxies_returns_snapshot(monkeypatch) -> None:
    from services.fireprox import ProxyMapping

    svc = _make_service(monkeypatch)
    m = ProxyMapping(
        original_url="https://a.com",
        proxy_url="https://proxy.aws/",
        proxy_id="abc",
        region=svc.aws_region,
        created_at=datetime.utcnow(),
    )
    svc._proxies["https://a.com"] = m
    assert svc.list_proxies() == [m]
