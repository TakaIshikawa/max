from __future__ import annotations

import json

from max.api import pipeline_budget_guardrail_trip_status_to_json


def test_pipeline_budget_guardrail_trip_sorts_hard_breaches_and_overage() -> None:
    report = json.loads(pipeline_budget_guardrail_trip_status_to_json({"breaches": [{"stage": "plan", "level": "soft", "limit": 100, "observed_usage": 90}, {"stage": "build", "level": "hard", "limit": 100, "observed_usage": 125}]}))

    assert report["breaches"][0]["stage"] == "build"
    assert report["breaches"][0]["overage"] == 25
    assert report["summary"]["severity"] == "critical"


def test_pipeline_budget_guardrail_trip_empty_is_ok() -> None:
    report = json.loads(pipeline_budget_guardrail_trip_status_to_json({}))

    assert report["summary"] == {"breach_count": 0, "hard_count": 0, "severity": "ok", "soft_count": 0}
