from __future__ import annotations

import json

from max.exports import build_feedback_weight_shift_report
from max.exports.feedback_weight_shift_report import render_feedback_weight_shift_report_json, render_feedback_weight_shift_report_markdown


def test_feedback_weight_shift_computes_deltas_and_status() -> None:
    rows = build_feedback_weight_shift_report(
        [
            {"dimension": "quality", "baseline": 0.5, "current": 0.52},
            {"dimension": "risk", "baseline_weight": 0.4, "proposed_weight": 0.6, "approvals": 3, "rejections": 1},
        ]
    )

    assert rows[0]["dimension"] == "risk"
    assert rows[0]["absolute_delta"] == 0.2
    assert rows[0]["relative_delta"] == 0.5
    assert rows[0]["shift_status"] == "review_required"
    assert rows[1]["shift_status"] == "stable"


def test_feedback_weight_shift_renderers_are_deterministic() -> None:
    rows = build_feedback_weight_shift_report([{"dimension": "x"}])

    assert json.loads(render_feedback_weight_shift_report_json(rows))[0]["dimension"] == "x"
    assert "| Dimension | Baseline |" in render_feedback_weight_shift_report_markdown(rows)
