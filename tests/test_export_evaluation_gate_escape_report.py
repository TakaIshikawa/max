from __future__ import annotations

import json

from max.exports.evaluation_gate_escape_report import generate_evaluation_gate_escape_report


def test_evaluation_gate_escape_report_joins_passed_evaluations_to_negative_outcomes() -> None:
    report = generate_evaluation_gate_escape_report(
        [
            {"idea_id": "idea-1", "dimension": "market", "score": 0.9},
            {"idea_id": "idea-2", "dimension": "market", "score": 0.8},
            {"idea_id": "idea-3", "dimension": "market", "score": 0.2},
        ],
        [
            {"idea_id": "idea-1", "outcome": "negative"},
            {"idea_id": "idea-2", "outcome": "positive"},
            {"idea_id": "idea-3", "outcome": "negative"},
        ],
    )

    assert report["summary"]["total_passed"] == 2
    assert report["summary"]["negative_outcomes"] == 1
    assert report["summary"]["escape_rate"] == 0.5
    assert report["escapes"] == [{"idea_id": "idea-1", "outcome": "negative", "dimensions": ["market"]}]
    json.dumps(report)


def test_evaluation_gate_escape_report_excludes_missing_outcomes_from_denominator() -> None:
    report = generate_evaluation_gate_escape_report(
        [
            {"idea_id": "idea-1", "dimension": "risk", "score": 0.9},
            {"idea_id": "idea-2", "dimension": "risk", "score": 0.8},
        ],
        [{"idea_id": "idea-1", "outcome": "negative"}],
    )

    assert report["summary"]["total_passed"] == 2
    assert report["summary"]["passed_with_outcome"] == 1
    assert report["summary"]["escape_rate"] == 1.0
    assert report["dimensions"][0]["passed_with_outcome"] == 1


def test_evaluation_gate_escape_report_attributes_escapes_to_each_dimension() -> None:
    report = generate_evaluation_gate_escape_report(
        [
            {"idea_id": "idea-1", "dimension": "market", "passed": True},
            {"idea_id": "idea-1", "dimension": "technical", "passed": True},
        ],
        [{"idea_id": "idea-1", "status": "failed"}],
    )

    assert [row["dimension"] for row in report["dimensions"]] == ["market", "technical"]
    assert all(row["negative_outcomes"] == 1 for row in report["dimensions"])
    assert report["escapes"][0]["dimensions"] == ["market", "technical"]


def test_evaluation_gate_escape_report_orders_dimensions_by_escape_rate_then_dimension() -> None:
    report = generate_evaluation_gate_escape_report(
        [
            {"idea_id": "a1", "dimension": "Alpha", "score": 1.0},
            {"idea_id": "a2", "dimension": "Alpha", "score": 1.0},
            {"idea_id": "b1", "dimension": "Beta", "score": 1.0},
            {"idea_id": "g1", "dimension": "Gamma", "score": 1.0},
            {"idea_id": "g2", "dimension": "Gamma", "score": 1.0},
        ],
        [
            {"idea_id": "a1", "outcome": "positive"},
            {"idea_id": "a2", "outcome": "negative"},
            {"idea_id": "b1", "outcome": "negative"},
            {"idea_id": "g1", "outcome": "positive"},
            {"idea_id": "g2", "outcome": "negative"},
        ],
    )

    assert [row["dimension"] for row in report["dimensions"]] == ["Beta", "Alpha", "Gamma"]
    assert [row["escape_rate"] for row in report["dimensions"]] == [1.0, 0.5, 0.5]
