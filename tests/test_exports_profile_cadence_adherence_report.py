from __future__ import annotations

import json

from max.exports.profile_cadence_adherence_report import generate_profile_cadence_adherence_report, render_profile_cadence_adherence_report_json, render_profile_cadence_adherence_report_markdown


def test_profile_cadence_adherence_report_summarizes_and_sorts() -> None:
    report = generate_profile_cadence_adherence_report([{"profile": "core", "expected_runs": 10, "completed_runs": 7, "missed_runs": 3, "late_runs": 1, "window_days": 30}, {"profile": "growth", "expected_runs": 10, "completed_runs": 8, "missed_runs": 2, "late_runs": 2, "window_days": 30}, {"profile": "ops", "expected_runs": 0, "completed_runs": 0}], warning_adherence_rate=0.9, critical_adherence_rate=0.75)
    assert report["schema_version"] == "max.profile_cadence_adherence_report.v1"
    assert report["kind"] == "max.profile_cadence_adherence_report"
    assert report["summary"] == {"profile_count": 3, "nonadherent_profile_count": 2, "average_adherence_rate": 0.8333, "total_missed_runs": 5, "total_late_runs": 3}
    assert [row["profile"] for row in report["profile_rows"]] == ["core", "growth", "ops"]
    assert [row["status"] for row in report["profile_rows"]] == ["critical", "warning", "healthy"]
    assert json.loads(render_profile_cadence_adherence_report_json(report))["summary"] == report["summary"]
    assert "Profile Cadence Adherence Report" in render_profile_cadence_adherence_report_markdown(report)
