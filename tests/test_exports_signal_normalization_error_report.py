from __future__ import annotations

from max.exports.signal_normalization_error_report import generate_signal_normalization_error_report


def test_signal_normalization_error_report_dedupes_ids_and_marks_required_critical() -> None:
    report = generate_signal_normalization_error_report(
        [
            {"source": "rss", "profile": "p", "field": "url", "error_type": "missing", "signal_id": "s2", "message": "missing url", "required": True},
            {"source": "rss", "profile": "p", "field": "url", "error_type": "missing", "signal_id": "s1", "message": "missing url", "required": True},
            {"source": "rss", "profile": "p", "field": "url", "error_type": "missing", "signal_id": "s2", "message": "blank url", "required": True},
        ]
    )

    row = report["rows"][0]
    assert row["failure_count"] == 3
    assert row["affected_signal_ids"] == ["s1", "s2"]
    assert row["top_error_examples"] == ["blank url", "missing url"]
    assert row["severity"] == "critical"
