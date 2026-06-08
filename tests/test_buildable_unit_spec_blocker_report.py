from __future__ import annotations

from max.exports import generate_buildable_unit_spec_blocker_report as exported
from max.exports.buildable_unit_spec_blocker_report import generate_buildable_unit_spec_blocker_report


def test_buildable_unit_spec_blocker_report_distinguishes_ready_units() -> None:
    report = generate_buildable_unit_spec_blocker_report([{"profile": "core", "ready": True}])

    assert exported is generate_buildable_unit_spec_blocker_report
    assert report["summary"]["status"] == "clear"
    assert report["rows"][0]["ready_units"] == 1
    assert report["rows"][0]["blocked_units"] == 0


def test_buildable_unit_spec_blocker_report_groups_missing_fields_and_evidence_gaps() -> None:
    report = generate_buildable_unit_spec_blocker_report(
        [
            {"profile": "core", "blocker_type": "spec", "missing_spec_fields": ["owner", "criteria"], "evidence_gaps": ["source"]},
            {"profile": "core", "blocker_type": "spec", "missing_fields": 1, "unresolved_evidence_gaps": 2},
        ]
    )

    row = report["rows"][0]
    assert row["profile"] == "core"
    assert row["blocker_type"] == "spec"
    assert row["blocked_units"] == 2
    assert row["missing_spec_fields"] == 3
    assert row["unresolved_evidence_gaps"] == 3
    assert row["status"] == "blocked"


def test_buildable_unit_spec_blocker_report_classifies_critical() -> None:
    report = generate_buildable_unit_spec_blocker_report(
        [{"profile": "core", "blocker": "evidence"} for _ in range(3)],
        critical_blocked_units=3,
    )

    assert report["summary"]["status"] == "critical"
    assert report["rows"][0]["status"] == "critical"
