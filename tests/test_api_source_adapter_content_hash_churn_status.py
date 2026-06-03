from __future__ import annotations

import json

from max.api import source_adapter_content_hash_churn_status_to_json


def test_source_adapter_content_hash_churn_status_calculates_rates_and_summary() -> None:
    data = json.loads(source_adapter_content_hash_churn_status_to_json({"warning_churn_rate": 0.2, "critical_churn_rate": 0.5, "adapters": [{"source": "rss", "hash_changes": 6, "fetched_count": 10, "window_hours": 24}, {"source": "api", "hash_changes": 2, "fetched_count": 10}, {"source": "docs", "hash_changes": 0, "fetched_count": 0}]}))

    assert data["status"] == "critical"
    assert data["summary"]["adapter_count"] == 3
    assert data["summary"]["noisy_adapter_count"] == 2
    assert data["summary"]["critical_count"] == 1
    assert data["summary"]["warning_count"] == 1
    assert [row["source"] for row in data["adapters"]] == ["rss", "api", "docs"]
    assert data["adapters"][0]["churn_rate"] == 0.6
