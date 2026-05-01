"""Tests for Redis-backed WAF reputation store."""

from __future__ import annotations

from unittest.mock import MagicMock

from services.waf_reputation import WafReputation, target_key


def test_target_key_https_strips_path() -> None:
    assert target_key("https://api.example.com/foo?x=1") == "https://api.example.com:443"


def test_target_key_bare_host() -> None:
    assert target_key("Example.COM") == "http://example.com:80"


def test_record_blocked_uses_pipeline() -> None:
    r = MagicMock()
    pipe = MagicMock()
    r.pipeline.return_value = pipe
    rep = WafReputation(redis_client=r)
    rep._ttl = 300
    rep.record_blocked("n1", "https://t.example:443", vendor="cf", evidence=["e1"], source="precheck")
    pipe.setex.assert_called()
    pipe.sadd.assert_called()
    pipe.expire.assert_called()
    pipe.execute.assert_called()
