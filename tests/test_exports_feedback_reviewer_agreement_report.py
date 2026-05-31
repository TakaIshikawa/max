from __future__ import annotations

import json

from max.exports import generate_feedback_reviewer_agreement_report
from max.exports.feedback_reviewer_agreement_report import render_feedback_reviewer_agreement_report_json, render_feedback_reviewer_agreement_report_markdown


def test_feedback_reviewer_agreement_computes_pairs_and_insufficient_coverage() -> None:
    report = generate_feedback_reviewer_agreement_report([{"profile": "p", "idea_id": "i1", "reviewer": "ann", "label": "approve"}, {"profile": "p", "idea_id": "i1", "reviewer": "bob", "label": "reject"}, {"profile": "p", "idea_id": "i2", "reviewer": "ann", "label": "approve"}, {"profile": "p", "idea_id": "i2", "reviewer": "bob", "label": "approve"}, {"profile": "p", "idea_id": "i3", "reviewer": "ann", "label": "approve"}])

    assert report["rows"][0]["agreement_percent"] == 50.0
    assert report["summary"]["disputed_count"] == 1
    assert report["summary"]["insufficient_coverage_count"] == 1
    assert "insufficient coverage" in render_feedback_reviewer_agreement_report_markdown(report)
    json.loads(render_feedback_reviewer_agreement_report_json(report))
