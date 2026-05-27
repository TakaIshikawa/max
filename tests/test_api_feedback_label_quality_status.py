from __future__ import annotations

import json

from max.api import feedback_label_quality_status_to_json


def test_feedback_label_quality_status_derives_clamps_and_averages_rates() -> None:
    parsed = json.loads(feedback_label_quality_status_to_json({"labelers": [{"labeler": "ok", "reviewed_count": 10, "disagreement_count": 1, "calibration_score": 0.9}, {"labeler": "bad", "disagreement_rate": 2, "calibration_score": 0.4}]}))

    assert [row["labeler"] for row in parsed["labelers"]] == ["bad", "ok"]
    assert parsed["labelers"][0]["disagreement_rate"] == 1.0
    assert parsed["labelers"][1]["disagreement_rate"] == 0.1
    assert parsed["summary"]["low_quality_count"] == 1
    assert parsed["summary"]["average_disagreement_rate"] == 0.55
