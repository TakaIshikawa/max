from __future__ import annotations

from max.exports.feedback_label_disagreement_report import build_feedback_label_disagreement_report, render_feedback_label_disagreement_report_markdown


def test_feedback_label_disagreement_report_derives_escalations() -> None:
    report = build_feedback_label_disagreement_report(
        [
            {"profile": "P", "idea_id": "a", "label": "approve", "reviewer_count": 5, "disagreement_count": 3},
            {"profile": "P", "idea_id": "b", "label": "reject", "reviewer_count": 4, "disagreement_count": 1},
        ],
        escalation_threshold=0.5,
    )

    assert report["label_disagreements"][0]["idea_id"] == "a"
    assert report["label_disagreements"][0]["disagreement_rate"] == 0.6
    assert report["summary"]["reviewed_item_count"] == 2
    assert report["summary"]["escalation_count"] == 1
    assert report["escalations"][0]["idea_id"] == "a"
    assert "- Escalations: 1" in render_feedback_label_disagreement_report_markdown(report)
