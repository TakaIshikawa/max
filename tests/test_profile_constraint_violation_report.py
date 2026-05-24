from __future__ import annotations

import json

from max.exports.profile_constraint_violation_report import (
    KIND,
    build_profile_constraint_violation_report,
    render_profile_constraint_violation_report_json,
)


def test_profile_constraint_violation_groups_violations() -> None:
    report = build_profile_constraint_violation_report(
        [
            {"profile": "enterprise", "constraint": "pii", "constraint_type": "privacy", "severity": "critical", "observed_value": "enabled", "expected_value": "blocked"},
            {"profile": "enterprise", "constraint": "source", "constraint_type": "coverage", "severity": "warning"},
            {"profile": "startup", "constraint": "budget", "passed": True},
        ]
    )

    assert report["kind"] == KIND
    assert report["summary"]["total_profiles"] == 2
    assert report["summary"]["profiles_with_violations"] == 1
    assert report["summary"]["critical_violations"] == 1
    assert report["summary"]["warning_violations"] == 1
    assert report["violations"][0]["constraint"] == "pii"
    assert report["violations_by_constraint_type"][1]["constraint_type"] == "privacy"
    assert json.loads(render_profile_constraint_violation_report_json(report))["summary"]["total_profiles"] == 2


def test_profile_constraint_violation_defaults_missing_fields() -> None:
    report = build_profile_constraint_violation_report([{}])

    assert report["constraint_rows"][0]["profile"] == "Unknown profile"
    assert report["constraint_rows"][0]["status"] == "violation"
