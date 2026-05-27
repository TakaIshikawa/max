from __future__ import annotations

from max.exports.safety_mitigation_escape_report import build_safety_mitigation_escape_report


def test_safety_mitigation_escape_report_excludes_covered_and_sorts() -> None:
    report = build_safety_mitigation_escape_report(
        [
            {"idea_id": "b", "spec_id": "s2", "category": "privacy", "severity": "medium", "covered": False},
            {"idea_id": "a", "spec_id": "s1", "category": "security", "severity": "critical", "covered": False},
            {"idea_id": "c", "spec_id": "s3", "category": "legal", "severity": "high", "covered": True},
        ]
    )

    assert [row["idea_id"] for row in report["missing_mitigations"]] == ["a", "b"]
    assert report["summary"]["mitigation_requirement_count"] == 3
    assert report["summary"]["covered_mitigation_count"] == 1
    assert report["summary"]["missing_mitigation_count"] == 2
