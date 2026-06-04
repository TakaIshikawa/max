from __future__ import annotations

import json

from max.api import feedback_outcome_confidence_status_to_json


def test_confident_approvals_are_high_confidence() -> None:
    report = json.loads(feedback_outcome_confidence_status_to_json({"outcomes": [{"idea_id": "a", "approvals": 9, "rejections": 1}]}))
    assert report["outcome_rows"][0]["status"] == "high_confidence"


def test_conflicting_reviewer_outcomes_are_ambiguous() -> None:
    report = json.loads(feedback_outcome_confidence_status_to_json({"rows": [{"idea_id": "a", "approvals": 3, "rejections": 2}]}))
    assert report["outcome_rows"][0]["status"] == "ambiguous"


def test_low_confidence_labels_are_flagged() -> None:
    report = json.loads(feedback_outcome_confidence_status_to_json({"items": [{"idea_id": "a", "approvals": 5, "low_confidence_labels": 3}]}))
    assert report["outcome_rows"][0]["status"] == "low_confidence"


def test_reversals_are_ambiguous() -> None:
    report = json.loads(feedback_outcome_confidence_status_to_json({"items": [{"idea_id": "a", "approvals": 10, "reversals": 1}]}))
    assert report["outcome_rows"][0]["status"] == "ambiguous"


def test_empty_histories_are_insufficient_data() -> None:
    report = json.loads(feedback_outcome_confidence_status_to_json({"items": [{"idea_id": "a"}]}))
    assert report["summary"]["insufficient_data_count"] == 1
