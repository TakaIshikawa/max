from __future__ import annotations

import json

from max.api import evaluation_golden_dataset_coverage_status_to_json


def test_evaluation_golden_dataset_coverage_status_flags_gaps_and_staleness() -> None:
    data = json.loads(evaluation_golden_dataset_coverage_status_to_json({"as_of": "2026-06-01T00:00:00Z", "stale_days": 30, "goldens": [{"dimension": "quality", "profile": "core", "golden_count": 4, "min_required": 10, "last_updated_at": "2026-01-01T00:00:00Z"}, {"dimension": "speed", "profile": "core", "golden_count": 10, "min_required": 10, "last_updated_at": "2026-05-20T00:00:00Z"}]}))

    assert data["status"] == "critical"
    assert data["summary"]["golden_set_count"] == 2
    assert data["summary"]["undercovered_count"] == 1
    assert data["summary"]["stale_count"] == 1
    assert data["goldens"][0]["coverage"] == 0.4
    assert data["goldens"][0]["status"] == "critical"


def test_evaluation_golden_dataset_coverage_status_accepts_items_alias_and_zero_minimum() -> None:
    data = json.loads(evaluation_golden_dataset_coverage_status_to_json({"items": [{"dimension": "x", "golden_count": 0, "min_required": 0}]}))

    assert data["goldens"][0]["coverage"] == 1.0
