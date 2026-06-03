from __future__ import annotations

import json

from max.api.feedback_label_drift_status import feedback_label_drift_status_to_json


def test_feedback_label_drift_status_includes_union_of_labels() -> None:
    report = json.loads(feedback_label_drift_status_to_json({"current_counts": {"good": 80, "bad": 20, "new": 20}, "baseline_counts": {"good": 50, "bad": 50}}, warning_delta=0.15, critical_delta=0.3))

    assert [row["label"] for row in report["label_rows"]] == ["bad", "good", "new"]
    assert report["label_rows"][0]["share_delta"] == 0.3333
    assert report["label_rows"][0]["status"] == "critical"
    assert report["summary"]["largest_drift_label"] == "bad"


def test_feedback_label_drift_status_handles_empty_counts() -> None:
    report = json.loads(feedback_label_drift_status_to_json({"current_counts": {}, "baseline_counts": {"bad": 2}}))

    assert report["label_rows"][0]["current_share"] == 0.0
    assert report["label_rows"][0]["baseline_share"] == 1.0
