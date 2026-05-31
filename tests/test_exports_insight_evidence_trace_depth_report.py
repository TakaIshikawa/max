from __future__ import annotations

from max.exports.insight_evidence_trace_depth_report import generate_insight_evidence_trace_depth_report, render_insight_evidence_trace_depth_report_markdown


def test_insight_evidence_trace_depth_prioritizes_missing_references() -> None:
    report = generate_insight_evidence_trace_depth_report(
        [
            {"insight_id": "shallow", "evidence_depth": 1, "source_ids": ["github"], "signal_ids": ["s1"]},
            {"insight_id": "broken", "evidence_depth": 3, "source_ids": ["github", "hn"], "signal_ids": ["s1"], "missing_references": ["unit:u1"]},
        ]
    )

    assert [row["insight_id"] for row in report["rows"]] == ["broken", "shallow"]
    assert report["rows"][0]["severity"] == "critical"
    assert report["rows"][1]["severity"] == "warn"
    assert "Restore missing upstream references" in render_insight_evidence_trace_depth_report_markdown(report)
