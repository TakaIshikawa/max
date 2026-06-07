from __future__ import annotations

from max.exports import generate_runtime_artifact_disk_pressure_report


def test_runtime_artifact_disk_pressure_groups_by_type_and_flags_thresholds() -> None:
    report = generate_runtime_artifact_disk_pressure_report(
        [
            {"artifact_type": "trace", "bytes": 60, "created_at": "2026-06-01T00:00:00"},
            {"artifact_type": "trace", "bytes": 50, "created_at": "2026-06-03T00:00:00"},
            {"artifact_type": "cache", "artifact_count": 3, "total_bytes": 90, "created_at": "2026-06-02T00:00:00"},
        ],
        max_bytes=100,
        max_count=2,
    )

    assert report["rows"][0]["artifact_type"] == "cache"
    assert report["rows"][0]["status"] == "warning"
    trace = report["rows"][1]
    assert trace["artifact_count"] == 2
    assert trace["total_bytes"] == 110
    assert trace["oldest_created_at"] == "2026-06-01T00:00:00"
    assert trace["newest_created_at"] == "2026-06-03T00:00:00"
    assert trace["status"] == "warning"


def test_runtime_artifact_disk_pressure_empty() -> None:
    assert generate_runtime_artifact_disk_pressure_report([])["summary"]["artifact_type_count"] == 0
