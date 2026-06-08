from __future__ import annotations

from max.exports import generate_runtime_artifact_retention_breach_report as exported
from max.exports.runtime_artifact_retention_breach_report import generate_runtime_artifact_retention_breach_report


def test_runtime_artifact_retention_breach_report_handles_empty_input() -> None:
    report = generate_runtime_artifact_retention_breach_report([])

    assert exported is generate_runtime_artifact_retention_breach_report
    assert report["summary"]["status"] == "healthy"
    assert report["summary"]["breach_count"] == 0
    assert report["rows"] == []


def test_runtime_artifact_retention_breach_report_groups_rollups() -> None:
    report = generate_runtime_artifact_retention_breach_report(
        [
            {"artifact_type": "log", "profile": "core", "status": "expired"},
            {"artifact_type": "log", "profile": "core", "retention_status": "missing"},
            {"artifact_type": "log", "profile": "core", "status": "retained"},
        ]
    )

    row = report["rows"][0]
    assert row["artifact_type"] == "log"
    assert row["artifact_count"] == 3
    assert row["breach_count"] == 2
    assert row["breach_rate"] == 0.6667
    assert row["status"] == "breach"


def test_runtime_artifact_retention_breach_report_classifies_critical() -> None:
    report = generate_runtime_artifact_retention_breach_report(
        [{"artifact_type": "log", "profile": "core", "status": "expired"} for _ in range(3)],
        critical_breach_count=3,
    )

    assert report["summary"]["status"] == "critical"
