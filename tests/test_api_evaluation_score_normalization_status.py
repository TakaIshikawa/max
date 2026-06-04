from __future__ import annotations

import json

from max.api import evaluation_score_normalization_status_to_json


def test_valid_scores_are_ok() -> None:
    report = json.loads(evaluation_score_normalization_status_to_json({"evaluations": [{"id": "a", "scores": {"impact": 0.4, "confidence": 0.4, "effort": 0.2}, "normalized_total": 1.0}]}))
    assert report["score_rows"][0]["status"] == "ok"


def test_negative_scores_are_flagged() -> None:
    report = json.loads(evaluation_score_normalization_status_to_json({"rows": [{"id": "a", "scores": {"impact": -1, "confidence": 0, "effort": 0}}]}))
    assert "below_min:impact" in report["score_rows"][0]["issues"]


def test_scores_above_max_are_flagged() -> None:
    report = json.loads(evaluation_score_normalization_status_to_json({"items": [{"id": "a", "scores": {"impact": 2, "confidence": 0, "effort": 0}}]}))
    assert "above_max:impact" in report["score_rows"][0]["issues"]


def test_missing_dimensions_are_flagged() -> None:
    report = json.loads(evaluation_score_normalization_status_to_json({"items": [{"id": "a", "scores": {"impact": 0.5}}]}))
    assert "missing:confidence" in report["score_rows"][0]["issues"]


def test_mixed_malformed_records_do_not_raise() -> None:
    report = json.loads(evaluation_score_normalization_status_to_json({"items": [{"id": "bad", "scores": "bad", "normalized_total": "x"}]}))
    assert report["score_rows"][0]["status"] == "critical"
