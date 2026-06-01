from __future__ import annotations

from max.spec.buildable_unit_graduation_criteria_plan import generate_buildable_unit_graduation_criteria_plan


def test_ready_units_meet_thresholds() -> None:
    plan = generate_buildable_unit_graduation_criteria_plan({"units": [{"id": "u1", "score": 0.9, "evidence_count": 3, "ready": True}]})
    assert plan["graduation_candidates"][0]["status"] == "ready"
    assert plan["summary"]["ready_count"] == 1


def test_blocked_units_get_remediation() -> None:
    plan = generate_buildable_unit_graduation_criteria_plan({"units": [{"id": "u1", "blockers": ["missing evidence"], "score": 1, "evidence_count": 9, "ready": True}]})
    assert plan["summary"]["blocked_count"] == 1
    assert plan["blocker_remediation"][0]["unit_id"] == "u1"
    assert plan["graduation_gates"] == []


def test_summary_counts_needs_review() -> None:
    plan = generate_buildable_unit_graduation_criteria_plan({"units": [{"id": "u1"}]})
    assert plan["summary"]["needs_review_count"] == 1
