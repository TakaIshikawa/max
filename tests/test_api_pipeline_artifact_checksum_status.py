from __future__ import annotations

import json

from max.api import pipeline_artifact_checksum_status_to_json


def test_pipeline_artifact_checksum_status_detects_failures() -> None:
    report = json.loads(
        pipeline_artifact_checksum_status_to_json(
            {
                "manifest_stale_hours": 24,
                "artifacts": [
                    {"artifact_id": "bad", "expected_checksum": "a", "actual_checksum": "b"},
                    {"artifact_id": "missing"},
                    {"artifact_id": "stale", "expected_checksum": "x", "actual_checksum": "x", "verified_at": "2026-05-30T00:00:00Z"},
                    {"artifact_id": "ok", "expected_checksum": "z", "actual_checksum": "z", "verified": True},
                ],
            },
            as_of="2026-06-01T12:00:00Z",
        )
    )

    assert report["status"] == "critical"
    assert report["summary"]["mismatch_count"] == 1
    assert report["summary"]["missing_checksum_count"] == 1
    assert report["summary"]["stale_manifest_count"] == 1
    assert report["artifacts"][0]["artifact_id"] == "bad"
    assert report["artifacts"][0]["expected_checksum"] == "a"
    assert report["artifacts"][0]["actual_checksum"] == "b"


def test_pipeline_artifact_checksum_status_handles_empty_and_nested_stage_artifacts() -> None:
    empty = json.loads(pipeline_artifact_checksum_status_to_json({}, as_of="2026-06-01T00:00:00Z"))
    nested = json.loads(
        pipeline_artifact_checksum_status_to_json(
            {
                "stages": [
                    {
                        "stage": "build",
                        "run_id": "r1",
                        "artifacts": [
                            {"artifact_id": "a1", "expected_checksum": "x", "actual_checksum": "x", "verified": True}
                        ],
                    }
                ]
            },
            as_of="2026-06-01T00:00:00Z",
        )
    )

    assert empty["status"] == "healthy"
    assert empty["summary"]["artifact_count"] == 0
    assert nested["artifacts"][0]["stage"] == "build"
    assert nested["summary"]["verified_count"] == 1
