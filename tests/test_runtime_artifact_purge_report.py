from __future__ import annotations

from max.exports import generate_runtime_artifact_purge_report as exported
from max.exports.runtime_artifact_purge_report import generate_runtime_artifact_purge_report


def test_runtime_artifact_purge_report_returns_clean_zero_totals() -> None:
    report = generate_runtime_artifact_purge_report([])

    assert exported is generate_runtime_artifact_purge_report
    assert report["summary"]["status"] == "clean"
    assert report["summary"]["reclaimable_bytes"] == 0
    assert report["rows"] == []


def test_runtime_artifact_purge_report_groups_and_excludes_retained_blocked_reclaimable_bytes() -> None:
    report = generate_runtime_artifact_purge_report(
        [
            {"kind": "log", "profile": "core", "eligible": True, "bytes": 100},
            {"kind": "log", "profile": "core", "status": "retained", "bytes": 200},
            {"kind": "log", "profile": "core", "status": "blocked", "bytes": 300},
            {"kind": "trace", "profile": "core", "status": "purged", "bytes": 400},
        ]
    )

    row = report["rows"][0]
    assert row["artifact_kind"] == "log"
    assert row["eligible_count"] == 2
    assert row["retained_count"] == 1
    assert row["blocked_purge_count"] == 1
    assert row["reclaimable_bytes"] == 100
    assert row["status"] == "blocked"
