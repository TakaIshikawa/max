from __future__ import annotations

import json

from max.exports.spec_evidence_trace_completeness_report import (
    KIND,
    build_spec_evidence_trace_completeness_report,
    render_spec_evidence_trace_completeness_report_json,
)


def test_spec_evidence_trace_completeness_scores_and_remediates() -> None:
    report = build_spec_evidence_trace_completeness_report(
        [
            {"spec_id": "spec-1", "title": "Checkout", "unit_ids": ["u1"], "insight_ids": ["i1"], "signal_ids": ["s1"], "owner": "pm"},
            {"spec_id": "spec-2", "unit_ids": ["u2"], "insight_ids": [], "signal_ids": ["s2"], "missing_links": ["insight"], "owner": "pm"},
            {"spec_id": "spec-3", "owner": "ops"},
        ]
    )

    assert report["kind"] == KIND
    assert report["summary"]["spec_count"] == 3
    assert report["summary"]["complete_spec_count"] == 1
    assert report["summary"]["remediation_count"] == 2
    assert [row["spec_id"] for row in report["remediation_queue"]] == ["spec-3", "spec-2"]
    assert report["spec_completeness"][0]["completeness_score"] == 0.0
    assert report["missing_evidence_chains"][0]["spec_id"] == "spec-2"
    assert json.loads(render_spec_evidence_trace_completeness_report_json(report))["summary"]["spec_count"] == 3


def test_spec_evidence_trace_completeness_defaults_missing_fields() -> None:
    report = build_spec_evidence_trace_completeness_report([{}])

    row = report["spec_completeness"][0]
    assert row["spec_id"] == "unknown-spec-1"
    assert row["title"] == "Untitled spec"
    assert row["owner"] == "Unassigned"
    assert row["completeness_score"] == 0.0
    assert report["remediation_queue"][0]["spec_id"] == "unknown-spec-1"
