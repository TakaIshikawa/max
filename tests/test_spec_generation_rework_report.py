from __future__ import annotations

import json

from max.exports.spec_generation_rework_report import build_spec_generation_rework_report, render_spec_generation_rework_report_json, render_spec_generation_rework_report_markdown


def test_spec_generation_rework_summarizes_revisions_reasons_and_queues() -> None:
    report = build_spec_generation_rework_report([
        {"unit_id": "u1", "spec_id": "s1", "revision": 1, "rejection_reason": "missing evidence", "reviewer": "Bea", "status": "rejected", "evidence_gap": "pricing source"},
        {"unit_id": "u1", "spec_id": "s1", "revision": 2, "rejection_reason": "missing evidence", "reviewer": "Bea", "status": "needs_rework"},
        {"unit_id": "u1", "spec_id": "s1", "revision": 3, "reviewer": "Ari", "status": "approved"},
        {"unit_id": "u2", "spec_id": "s2", "revision": 1, "rejection_reason": "scope", "reviewer": "Ari", "status": "pending"},
    ])

    assert report["summary"]["spec_count"] == 2
    assert report["summary"]["average_revisions_per_spec"] == 2.0
    assert report["summary"]["high_rework_count"] == 1
    assert report["top_rejection_reasons"][0] == {"reason": "missing evidence", "count": 2}
    assert report["reviewer_queues"][0] == {"reviewer": "Bea", "count": 2}
    assert "s1: 3 revisions" in render_spec_generation_rework_report_markdown(report)
    assert json.loads(render_spec_generation_rework_report_json(report))["kind"] == "max.spec_generation_rework_report"
