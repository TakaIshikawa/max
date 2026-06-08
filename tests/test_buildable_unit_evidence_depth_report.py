from __future__ import annotations

from max.exports import generate_buildable_unit_evidence_depth_report as exported
from max.exports.buildable_unit_evidence_depth_report import generate_buildable_unit_evidence_depth_report


def test_buildable_unit_evidence_depth_report_marks_ready_units() -> None:
    report = generate_buildable_unit_evidence_depth_report(
        [{"unit_id": "ready", "signals": [1, 2, 3], "insights": ["market"], "sources": ["crm", "rss"]}]
    )

    assert exported is generate_buildable_unit_evidence_depth_report
    assert report["rows"][0]["status"] == "ready"
    assert report["rows"][0]["signal_count"] == 3
    assert report["summary"]["ready_count"] == 1


def test_buildable_unit_evidence_depth_report_marks_thin_units_below_thresholds() -> None:
    report = generate_buildable_unit_evidence_depth_report(
        [{"unit_id": "thin", "signals": [1], "insights": [], "sources": ["crm"]}]
    )

    assert report["rows"][0]["status"] == "thin"
    assert report["rows"][0]["missing_evidence_fields"] == []
    assert report["summary"]["thin_count"] == 1


def test_buildable_unit_evidence_depth_report_marks_blocked_when_evidence_containers_missing() -> None:
    report = generate_buildable_unit_evidence_depth_report(
        [
            {"unit_id": "ready", "signals": [1, 2, 3], "insights": [1], "sources": [1]},
            {"unit_id": "blocked", "signals": [1, 2, 3], "sources": [1]},
        ]
    )

    assert [row["unit_id"] for row in report["rows"]] == ["blocked", "ready"]
    assert report["rows"][0]["status"] == "blocked"
    assert report["rows"][0]["missing_evidence_fields"] == ["insights"]


def test_buildable_unit_evidence_depth_report_handles_empty_input() -> None:
    report = generate_buildable_unit_evidence_depth_report([])

    assert report["summary"]["unit_count"] == 0
    assert report["rows"] == []
