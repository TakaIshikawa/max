from __future__ import annotations

from max.exports.feedback_recency_decay_report import generate_feedback_recency_decay_report


def test_feedback_recency_decay_buckets_and_escalates_high_weight_old_feedback() -> None:
    report = generate_feedback_recency_decay_report(
        [{"profile": "p", "outcome_label": "won", "last_seen_at": "2026-01-01", "weight": 0.9}, {"profile": "p", "outcome_label": "lost", "last_seen_at": "2026-05-30", "weight": 0.2}],
        as_of="2026-05-31",
    )

    assert report["rows"][0]["decay_bucket"] == "expired"
    assert report["rows"][0]["severity"] == "critical"
    assert report["rows"][0]["oldest_feedback_age_days"] == 150
