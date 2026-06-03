from __future__ import annotations

import json

from max.api import source_adapter_token_bucket_status_to_json


def test_source_adapter_token_bucket_status_computes_remaining_ratio_and_sorts() -> None:
    data = json.loads(source_adapter_token_bucket_status_to_json({"adapters": [{"source": "rss", "bucket_capacity": 100, "tokens_remaining": 0, "requests_waiting": 2}, {"source": "web", "bucket_capacity": 100, "tokens_remaining": 10, "requests_waiting": 0}, {"source": "api", "bucket_capacity": 50, "tokens_remaining": 30, "requests_waiting": 1}]}))
    assert data["summary"] == {"status": "critical", "adapter_count": 3, "constrained_adapter_count": 3, "critical_count": 1, "warning_count": 2, "total_requests_waiting": 3, "lowest_remaining_ratio": 0.0}
    assert [row["source"] for row in data["adapters"]] == ["rss", "api", "web"]
    assert data["adapters"][1]["remaining_ratio"] == 0.6
