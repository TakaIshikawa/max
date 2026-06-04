from __future__ import annotations

from max.exports.spec_acceptance_criteria_risk_report import generate_spec_acceptance_criteria_risk_report


def test_accepts_dict_like_spec_records() -> None:
    report = generate_spec_acceptance_criteria_risk_report([{"spec_id": "s1", "acceptance_criteria": ["passes tests", "handles errors"], "verification_command": "pytest"}])
    assert report["rows"][0]["spec_id"] == "s1"
    assert report["rows"][0]["risk"] == "low"


def test_rows_include_counts_and_verification() -> None:
    report = generate_spec_acceptance_criteria_risk_report([{"id": "s1", "criteria": ["TBD behavior"], "verification": ""}])
    row = report["rows"][0]
    assert row["criteria_count"] == 1
    assert row["has_verification"] is False
    assert row["vague_criteria_count"] == 1
    assert row["risk"] == "high"


def test_vague_detection_uses_deterministic_keywords() -> None:
    report = generate_spec_acceptance_criteria_risk_report([{"id": "s1", "criteria": ["Do reasonable validation"], "verification": "pytest"}])
    assert report["rows"][0]["vague_criteria_count"] == 1
    assert report["rows"][0]["risk"] == "medium"
