from __future__ import annotations

import json

from max.api import model_usage_anomaly_status_to_json


def test_model_usage_anomaly_status_derives_delta_and_sorts_by_cost_delta() -> None:
    parsed = json.loads(model_usage_anomaly_status_to_json({"usage": [{"model": "small", "current_tokens": 200, "baseline_tokens": 100, "current_cost_usd": 1, "baseline_cost_usd": 0.5}, {"model": "large", "current_tokens": 300, "baseline_tokens": 100, "current_cost_usd": 20, "baseline_cost_usd": 5}]}))

    assert [row["model"] for row in parsed["models"]] == ["large", "small"]
    assert parsed["models"][0]["delta_ratio"] == 2.0
    assert parsed["models"][0]["status"] == "critical"


def test_model_usage_anomaly_status_handles_missing_baseline() -> None:
    parsed = json.loads(model_usage_anomaly_status_to_json({"models": [{"model": "new", "current_tokens": 10}]}))

    assert parsed["models"][0]["baseline_missing"] is True
    assert parsed["models"][0]["status"] == "medium"
    assert parsed["summary"]["baseline_missing_count"] == 1
