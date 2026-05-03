"""Tests for Redis-backed worker WAF block aggregation."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from services.worker_waf_status import get_worker_waf_status


@patch("services.worker_waf_status.redis.from_url")
def test_redis_connection_failure(mock_from_url):
    mock_from_url.side_effect = OSError("connection refused")
    out = get_worker_waf_status()
    assert out["redis_connected"] is False
    assert out["error"]
    assert out["blocked_by_node"] == {}


@patch("services.worker_waf_status.redis.from_url")
def test_groups_blocks_by_node_sorted_targets(mock_from_url):
    fake = MagicMock()
    fake.ping.return_value = True
    fake.scan_iter.return_value = iter(
        [
            "waf:block:node-b|https|//|x|com|443",
            "waf:block:node-a|https|//|y|com|443",
        ]
    )

    def get_side_effect(key):
        if "node-a" in key:
            return json.dumps(
                {
                    "node": "node-a",
                    "target": "https://y.com:443",
                    "vendor": None,
                    "source": "precheck",
                    "blocked_at": 1000.0,
                    "evidence": ["e1"],
                }
            )
        return json.dumps(
            {
                "node": "node-b",
                "target": "https://x.com:443",
                "vendor": "cf",
                "source": "secondary",
                "blocked_at": 1001.0,
                "evidence": [],
            }
        )

    fake.ttl.return_value = 90
    fake.get.side_effect = get_side_effect
    mock_from_url.return_value = fake

    out = get_worker_waf_status()
    assert out["redis_connected"] is True
    assert out["error"] is None
    by_node = out["blocked_by_node"]
    assert set(by_node.keys()) == {"node-a", "node-b"}
    assert [x["target"] for x in by_node["node-a"]] == ["https://y.com:443"]
    assert [x["target"] for x in by_node["node-b"]] == ["https://x.com:443"]
    assert by_node["node-b"][0]["ttl_seconds"] == 90
    fake.close.assert_called_once()


@patch("services.worker_waf_status.redis.from_url")
def test_skips_expired_and_malformed(mock_from_url):
    fake = MagicMock()
    fake.ping.return_value = True
    fake.scan_iter.return_value = iter(["waf:block:n:k1", "waf:block:n:k2", "waf:block:n:k3"])
    fake.ttl.side_effect = [-2, 10, 10]
    fake.get.side_effect = [None, "{not-json", json.dumps({"node": "", "target": "https://z:443"})]
    mock_from_url.return_value = fake

    out = get_worker_waf_status()
    assert out["blocked_by_node"] == {}
