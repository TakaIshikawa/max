from __future__ import annotations

from max.exports.idea_evidence_gap_report import generate_idea_evidence_gap_report


def test_accepts_evidence_role_collections() -> None:
    report = generate_idea_evidence_gap_report([{"unit_id": "u1", "evidence_roles": ["problem", "market", "solution"]}])
    assert report["rows"][0]["missing_roles"] == []
    assert report["rows"][0]["severity"] == "low"


def test_missing_roles_are_reported_per_unit() -> None:
    report = generate_idea_evidence_gap_report([{"unit_id": "u1", "evidence": [{"role": "problem"}]}])
    assert report["rows"][0]["missing_roles"] == ["market", "solution"]
    assert report["rows"][0]["total_missing_roles"] == 2


def test_severity_escalates_for_missing_problem_evidence() -> None:
    report = generate_idea_evidence_gap_report([{"unit_id": "solution-only", "evidence_roles": ["solution"]}, {"unit_id": "market-gap", "evidence_roles": ["problem", "solution"]}])
    assert [row["severity"] for row in report["rows"]] == ["high", "medium"]
