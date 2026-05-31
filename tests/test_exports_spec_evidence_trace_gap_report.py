from __future__ import annotations

from max.exports.spec_evidence_trace_gap_report import generate_spec_evidence_trace_gap_report, render_spec_evidence_trace_gap_report_markdown


def test_spec_evidence_trace_gap_separates_gap_types_and_omits_complete_specs() -> None:
    report = generate_spec_evidence_trace_gap_report(
        [
            {"spec_id": "complete", "unit_ids": ["u1"], "insight_ids": ["i1"], "signal_ids": ["s1"]},
            {"spec_id": "draft-gap", "unit_ids": ["u2"], "status": "draft"},
            {"spec_id": "published-gap", "status": "published", "insight_ids": ["i2"]},
        ]
    )

    assert [row["spec_id"] for row in report["rows"]] == ["published-gap", "draft-gap"]
    assert report["rows"][0]["missing_unit_link"] is True
    assert report["rows"][0]["missing_signal_link"] is True
    assert report["rows"][0]["severity"] == "critical"
    assert report["rows"][1]["missing_insight_link"] is True
    assert report["summary"]["missing_unit_count"] == 1


def test_spec_evidence_trace_gap_markdown_includes_remediation_hints() -> None:
    report = generate_spec_evidence_trace_gap_report([{"spec_id": "approved", "status": "approved"}])
    markdown = render_spec_evidence_trace_gap_report_markdown(report)

    assert "unit: Attach the originating buildable unit" in markdown
    assert "insight: Link the synthesized insight" in markdown
    assert "signal: Backfill source signal IDs" in markdown
