from __future__ import annotations

from max.exports import generate_buildable_unit_approval_readiness_report


def test_buildable_unit_approval_readiness_flags_ready_review_and_blocked() -> None:
    report = generate_buildable_unit_approval_readiness_report(
        [
            {"unit_id": "u-ready", "recommendation": "approved", "evidence": ["e1"], "acceptance_criteria": ["c1"]},
            {"unit_id": "u-review", "recommendation": "approved", "evidence": ["e1"]},
            {"unit_id": "u-blocked", "recommendation": "approved", "evidence_count": 2, "acceptance_criteria_count": 1, "spec_blockers": ["missing owner"]},
        ]
    )

    assert report["summary"] == {"unit_count": 3, "ready_count": 1, "needs_review_count": 1, "blocked_count": 1}
    assert [(row["unit_id"], row["status"]) for row in report["rows"]] == [("u-blocked", "blocked"), ("u-review", "needs_review"), ("u-ready", "ready")]
    assert set(report["rows"][0]) >= {"unit_id", "recommendation", "evidence_count", "acceptance_criteria_count", "blocker_count", "status"}


def test_buildable_unit_approval_readiness_handles_empty_units() -> None:
    report = generate_buildable_unit_approval_readiness_report([])

    assert report["summary"]["unit_count"] == 0
    assert report["rows"] == []
