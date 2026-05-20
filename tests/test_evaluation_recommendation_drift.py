from __future__ import annotations

import json

from max.exports.evaluation_recommendation_drift import (
    build_evaluation_recommendation_drift_report,
    render_evaluation_recommendation_drift_json,
    render_evaluation_recommendation_drift_markdown,
)


def test_evaluation_recommendation_drift_counts_transitions_and_distribution() -> None:
    report = build_evaluation_recommendation_drift_report(
        [
            {"idea_id": "checkout", "idea": "Fast checkout", "evaluated_at": "2026-05-01", "recommendation": "monitor", "score": 0.62, "driver": "weak evidence"},
            {"idea_id": "checkout", "idea": "Fast checkout", "evaluated_at": "2026-05-10", "recommendation": "approve", "score": 0.81, "driver": "conversion lift"},
            {"idea_id": "onboarding", "idea": "Guided onboarding", "evaluated_at": "2026-05-02", "recommendation": "approve", "score": 0.74, "driver": "customer pull"},
            {"idea_id": "onboarding", "idea": "Guided onboarding", "evaluated_at": "2026-05-12", "recommendation": "approve", "score": 0.79, "driver": "customer pull"},
        ],
        large_drift_threshold=0.25,
    )

    assert report["summary"]["idea_count"] == 2
    assert report["summary"]["transition_count"] == 2
    assert report["summary"]["recommendation_change_count"] == 1
    assert report["summary"]["average_score_delta"] == 0.12
    assert report["recommendation_distribution"] == [{"recommendation": "approve", "count": 2}]
    assert report["transition_counts"] == [
        {"transition": "approve -> approve", "count": 1},
        {"transition": "monitor -> approve", "count": 1},
    ]
    assert report["large_drifts"][0]["transition"] == "monitor -> approve"
    assert json.loads(render_evaluation_recommendation_drift_json(report))["summary"]["idea_count"] == 2


def test_evaluation_recommendation_drift_flags_large_score_changes_and_drivers() -> None:
    report = build_evaluation_recommendation_drift_report(
        [
            {"idea_id": "pricing", "evaluated_at": "2026-05-01", "recommendation": "approve", "score": 0.88, "driver": "baseline"},
            {"idea_id": "pricing", "evaluated_at": "2026-05-09", "recommendation": "monitor", "score": 0.5, "drift_driver": "margin risk"},
            {"idea_id": "search", "evaluated_at": "2026-05-03", "recommendation": "reject", "score": 0.2, "driver": "baseline"},
            {"idea_id": "search", "evaluated_at": "2026-05-11", "recommendation": "reject", "score": 0.47, "reason": "new evidence"},
        ],
        large_drift_threshold=0.25,
    )

    assert [drift["idea_id"] for drift in report["large_drifts"]] == ["pricing", "search"]
    assert report["top_drift_drivers"] == [
        {"driver": "margin risk", "drift_count": 1, "average_absolute_score_delta": 0.38},
        {"driver": "new evidence", "drift_count": 1, "average_absolute_score_delta": 0.27},
    ]
    markdown = render_evaluation_recommendation_drift_markdown(report)
    assert "approve -> monitor" in markdown
    assert "- Driver: margin risk" in markdown


def test_evaluation_recommendation_drift_empty_input_is_deterministic() -> None:
    report = build_evaluation_recommendation_drift_report([])

    assert report["summary"] == {
        "snapshot_count": 0,
        "idea_count": 0,
        "transition_count": 0,
        "recommendation_change_count": 0,
        "large_drift_count": 0,
        "average_score_delta": 0.0,
    }
    assert report["recommendation_distribution"] == []
    assert report["transition_counts"] == []
    assert report["large_drifts"] == []
    assert "No large recommendation drifts were supplied." in render_evaluation_recommendation_drift_markdown(report)
