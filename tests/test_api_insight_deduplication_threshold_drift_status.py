from __future__ import annotations

import json

from max.api import insight_deduplication_threshold_drift_status_to_json


def test_threshold_drift_ranks_delta_and_escalates_error_rates() -> None:
    report = json.loads(insight_deduplication_threshold_drift_status_to_json({"thresholds": [{"profile": "small-drift", "current_threshold": 0.8, "baseline_threshold": 0.78, "merge_error_rate": 0.2}, {"profile": "large-drift", "current_threshold": 0.9, "baseline_threshold": 0.7}, {"profile": "ok", "current_threshold": 0.8, "baseline_threshold": 0.8}]}))

    assert report["rows"][0]["profile"] == "large-drift"
    assert report["rows"][0]["threshold_delta"] == 0.2
    assert {row["profile"]: row["status"] for row in report["rows"]}["small-drift"] == "critical"
