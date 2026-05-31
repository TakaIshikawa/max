from __future__ import annotations

from max.exports.adapter_payload_shape_drift_report import generate_adapter_payload_shape_drift_report


def test_adapter_payload_shape_drift_reports_missing_unexpected_and_empty_sources() -> None:
    report = generate_adapter_payload_shape_drift_report(
        [{"source": "jobs", "payload": {"id": "1", "title": "T", "extra": "x"}}],
        {"jobs": ["id", "title", "url"], "empty": ["id"]},
    )

    jobs = next(row for row in report["rows"] if row["source"] == "jobs")
    empty = next(row for row in report["rows"] if row["source"] == "empty")
    assert jobs["missing_fields"] == ["url"]
    assert jobs["unexpected_fields"] == ["extra"]
    assert jobs["severity"] == "critical"
    assert empty["sample_count"] == 0
    assert empty["severity"] == "warn"
