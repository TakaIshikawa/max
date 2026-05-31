from __future__ import annotations

import json

from max.api import adapter_rate_limit_exhaustion_status_to_json


def test_adapter_rate_limit_exhaustion_sorts_exhausted_before_warning_and_healthy() -> None:
    report = json.loads(adapter_rate_limit_exhaustion_status_to_json({"adapters": [{"adapter": "healthy", "limit": 100, "remaining": 80}, {"adapter": "empty", "limit": 100, "remaining": 0}, {"adapter": "low", "limit": 100, "remaining": 5}]}))

    assert [row["adapter"] for row in report["adapters"]] == ["empty", "low", "healthy"]
    assert report["summary"]["severity"] == "critical"
    assert report["summary"]["exhausted_count"] == 1


def test_adapter_rate_limit_exhaustion_empty_is_ok() -> None:
    report = json.loads(adapter_rate_limit_exhaustion_status_to_json({}))

    assert report["summary"]["severity"] == "ok"
