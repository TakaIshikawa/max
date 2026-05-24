from __future__ import annotations

import json

from max.exports.tact_spec_generation_failure_report import (
    KIND,
    build_tact_spec_generation_failure_report,
    render_tact_spec_generation_failure_report_json,
)


def test_tact_spec_generation_failure_groups_and_normalizes() -> None:
    report = build_tact_spec_generation_failure_report(
        [
            {"unit_id": "u1", "template": "launch", "reason": "Timeout while rendering", "retryable": True, "owner": "pm"},
            {"unit_id": "u2", "template": "launch", "reason": "missing evidence links", "status": "resolved"},
            {"unit_id": "u1", "template": "security", "reason": "template missing variable"},
        ]
    )

    assert report["kind"] == KIND
    assert report["summary"]["total_failures"] == 3
    assert report["summary"]["affected_units"] == 2
    assert report["summary"]["affected_templates"] == 2
    assert report["summary"]["unresolved_failures"] == 2
    assert report["failure_rows"][0]["reason"] == "timeout"
    assert report["failures_by_template"][0]["template"] == "launch"
    assert json.loads(render_tact_spec_generation_failure_report_json(report))["summary"]["total_failures"] == 3


def test_tact_spec_generation_failure_defaults_missing_fields() -> None:
    report = build_tact_spec_generation_failure_report([{}])

    assert report["failure_rows"][0]["unit_id"] == "unknown-unit-1"
    assert report["failure_rows"][0]["reason"] == "unknown"
