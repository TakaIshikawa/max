from __future__ import annotations

from max.exports.runtime_artifact_retention_report import generate_runtime_artifact_retention_report


def test_runtime_artifact_retention_report_grouped_totals() -> None:
    report = generate_runtime_artifact_retention_report([{"artifact_type": "log", "run_id": "r1", "status": "retained"}, {"artifact_type": "log", "run_id": "r1", "status": "expired"}, {"artifact_type": "trace", "run_id": "r2", "status": "missing"}])
    assert report["summary"]["artifact_count"] == 3
    assert report["summary"]["breach_rate"] == 0.6667
    assert report["artifact_types"][0]["breach_count"] == 1
    assert report["run_ids"][0]["run_id"] == "r1"


def test_runtime_artifact_retention_report_zero_artifact_output() -> None:
    report = generate_runtime_artifact_retention_report([])
    assert report["summary"]["status"] == "healthy"
    assert report["summary"]["breach_rate"] == 0.0
    assert report["recommended_actions"] == []


def test_runtime_artifact_retention_report_top_reason_ordering() -> None:
    report = generate_runtime_artifact_retention_report([{"status": "expired", "reason": "ttl"}, {"status": "missing", "reason": "upload_failed"}, {"status": "expired", "reason": "ttl"}, {"status": "oversized", "reason": "archive_limit"}])
    assert report["top_breach_reasons"] == [{"reason": "ttl", "count": 2}, {"reason": "archive_limit", "count": 1}, {"reason": "upload_failed", "count": 1}]
