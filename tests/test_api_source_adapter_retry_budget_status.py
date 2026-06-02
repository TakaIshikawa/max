from __future__ import annotations

import json

from max.api import source_adapter_retry_budget_status_to_json


def test_retry_budget_status_sorts_counts_and_handles_zero_budget() -> None:
    report = json.loads(source_adapter_retry_budget_status_to_json({"warning_ratio": 0.7, "critical_ratio": 0.95, "adapters": [{"adapter": "ok", "retries_used": 1, "retry_budget": 10}, {"source": "warn", "retries_used": 7, "retry_budget": 10}, {"adapter": "empty", "retries_used": 1, "failed_attempts": 2}]}))

    assert [row["adapter"] for row in report["adapters"]] == ["empty", "warn", "ok"]
    assert report["adapters"][0]["status"] == "critical"
    assert report["adapters"][0]["consumption_ratio"] == 1.0
    assert report["totals"]["retries_used"] == 9
    assert report["exhausted_count"] == 1
    assert report["warning_count"] == 1
    assert report["status"] == "critical"
