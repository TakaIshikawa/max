from __future__ import annotations

from max.exports import generate_buildable_unit_graduation_criteria_report as exported
from max.exports.buildable_unit_graduation_criteria_report import generate_buildable_unit_graduation_criteria_report


def test_buildable_unit_graduation_criteria_report_groups_ready_and_blocked_rows() -> None:
    report = generate_buildable_unit_graduation_criteria_report(
        [
            {"profile": "b2b", "buildable_unit_id": "unit-b", "criteria": [{"name": "evidence", "passed": True, "required": True}, {"name": "launch plan", "passed": False, "required": False}]},
            {"profile": "b2b", "buildable_unit_id": "unit-a", "criteria": [{"name": "owner", "status": "passed", "required": True}, {"name": "security review", "status": "failed", "required": True}]},
        ]
    )

    assert exported is generate_buildable_unit_graduation_criteria_report
    assert report["summary"] == {"row_count": 2, "ready_count": 1, "blocked_count": 1}
    assert report["rows"] == [
        {"profile": "b2b", "buildable_unit_id": "unit-a", "passed_count": 1, "failed_count": 1, "missing_required_criteria": ["security review"], "pass_rate": 0.5, "status": "blocked"},
        {"profile": "b2b", "buildable_unit_id": "unit-b", "passed_count": 1, "failed_count": 1, "missing_required_criteria": [], "pass_rate": 0.5, "status": "ready"},
    ]


def test_buildable_unit_graduation_criteria_report_empty_input() -> None:
    assert generate_buildable_unit_graduation_criteria_report([])["rows"] == []
