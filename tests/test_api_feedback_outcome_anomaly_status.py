from __future__ import annotations

import json

from max.api import feedback_outcome_anomaly_status_to_json


def test_feedback_outcome_anomaly_status_marks_low_sample_and_coerces_counts() -> None:
    report = json.loads(feedback_outcome_anomaly_status_to_json({"segments": [{"segment": "ok", "approved_count": 8, "rejected_count": 2, "baseline_approval_rate": 0.75}, {"profile": "crit", "approved_count": 1, "rejected_count": 9, "baseline_approval_rate": 0.8}, {"reviewer": "small", "approved_count": "bad", "rejected_count": 2, "neutral_count": -1, "baseline_approval_rate": 1.0}]}, minimum_sample_size=5, warning_delta=0.1, critical_delta=0.3))

    assert [row["segment"] for row in report["segment_rows"]] == ["crit", "small", "ok"]
    assert report["segment_rows"][0]["status"] == "critical"
    assert report["segment_rows"][1]["status"] == "insufficient_data"
    assert report["segment_rows"][1]["approved_count"] == 0
