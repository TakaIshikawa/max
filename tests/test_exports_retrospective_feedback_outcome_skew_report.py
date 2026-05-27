from __future__ import annotations

from max.exports import generate_retrospective_feedback_outcome_skew_report


def test_retrospective_feedback_outcome_skew_report_respects_minimum_sample() -> None:
    report = generate_retrospective_feedback_outcome_skew_report(
        [
            {"profile": "p1", "category": "ux", "source": "review", "outcome": "approved"},
            {"profile": "p1", "category": "ux", "source": "review", "outcome": "approved"},
            {"profile": "p1", "category": "ux", "source": "review", "outcome": "approved"},
            {"profile": "p2", "category": "infra", "source": "review", "outcome": "rejected"},
        ],
        dimensions=["profile"],
        minimum_sample=3,
        skew_threshold=0.8,
    )

    assert report["summary"]["total_feedback"] == 4
    assert report["summary"]["dimensions_analyzed"] == ["profile"]
    assert report["summary"]["flagged_segments"] == 1
    assert report["findings"][0]["segment"] == "p1"
    assert report["findings"][0]["skew_type"] == "approval"
