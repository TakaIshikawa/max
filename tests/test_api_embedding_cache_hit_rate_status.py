from __future__ import annotations

import json

from max.api import embedding_cache_hit_rate_status_to_json


def test_embedding_cache_hit_rate_status_orders_low_namespaces() -> None:
    report = json.loads(embedding_cache_hit_rate_status_to_json({"warning_min_hit_rate": 0.8, "critical_min_hit_rate": 0.5, "namespaces": [{"namespace": "good", "hits": 90, "misses": 10}, {"namespace": "bad", "hits": 20, "misses": 80}, {"namespace": "warn", "hits": 70, "misses": 30}]}))

    assert report["summary"]["status"] == "critical"
    assert report["summary"]["hit_rate"] == 0.6
    assert [row["namespace"] for row in report["low_hit_rate_namespaces"]] == ["bad", "warn"]


def test_embedding_cache_hit_rate_status_zero_volume_is_healthy() -> None:
    report = json.loads(embedding_cache_hit_rate_status_to_json({"namespaces": [{"namespace": "empty"}]}))

    assert report["summary"]["status"] == "healthy"
    assert report["namespaces"][0]["hit_rate"] == 0.0
