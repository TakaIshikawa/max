from __future__ import annotations

from max.exports.signal_annotation_gap_report import generate_signal_annotation_gap_report


def test_signal_annotation_gap_counts_fields_and_escalates_by_age() -> None:
    report = generate_signal_annotation_gap_report(
        [
            {"source": "github", "profile": "p", "created_at": "2026-04-01", "role": "dev"},
            {"source": "github", "profile": "p", "created_at": "2026-05-30", "role": "dev", "market": "smb", "problem": "x", "solution": "y"},
        ],
        as_of="2026-05-31",
    )

    assert report["summary"]["gap_signal_count"] == 1
    assert report["rows"][0]["age_bucket"] == "30d+"
    assert report["rows"][0]["missing_fields"] == {"market": 1, "problem": 1, "solution": 1}
    assert report["rows"][0]["severity"] == "critical"
