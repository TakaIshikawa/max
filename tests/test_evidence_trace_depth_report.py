from __future__ import annotations

import json

from max.exports import build_evidence_trace_depth_report
from max.exports.evidence_trace_depth_report import render_evidence_trace_depth_report_json, render_evidence_trace_depth_report_markdown


def test_evidence_trace_depth_normalizes_aliases_and_sorts_risk() -> None:
    rows = build_evidence_trace_depth_report(
        [
            {"idea_id": "ok", "signals": ["s1"], "insights": ["i1"], "units": ["u1"], "tact_spec_id": "sp1"},
            {"idea_id": "bad", "signal_ids": ["s2"]},
        ]
    )

    assert rows[0]["idea_id"] == "bad"
    assert rows[0]["trace_depth"] == 1
    assert rows[0]["missing_link_count"] == 3
    assert rows[0]["risk_level"] == "high"
    assert rows[1]["evidence_count"] == 4


def test_evidence_trace_depth_renderers() -> None:
    rows = build_evidence_trace_depth_report([{"idea_id": "x"}])

    assert json.loads(render_evidence_trace_depth_report_json(rows))[0]["risk_level"] == "high"
    assert "| Idea | Spec |" in render_evidence_trace_depth_report_markdown(rows)
