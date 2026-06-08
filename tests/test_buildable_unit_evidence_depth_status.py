from __future__ import annotations

import json

from max.api.buildable_unit_evidence_depth_status import buildable_unit_evidence_depth_status_to_json


def test_buildable_unit_evidence_depth_status_ready() -> None:
    report = json.loads(buildable_unit_evidence_depth_status_to_json({"units": [{"unit_id": "u1", "profile": "core", "signal_count": 2, "insight_count": 1, "distinct_source_count": 2}]}))

    assert report["units"][0]["status"] == "ready"
    assert report["units"][0]["missing_depth_reasons"] == []


def test_buildable_unit_evidence_depth_status_missing_insights_blocks() -> None:
    report = json.loads(buildable_unit_evidence_depth_status_to_json({"units": [{"unit_id": "u1", "signal_count": 2, "insight_count": 0, "distinct_source_count": 2}]}))

    assert report["units"][0]["status"] == "blocked"
    assert report["units"][0]["missing_depth_reasons"] == ["insights"]


def test_buildable_unit_evidence_depth_status_missing_source_diversity_is_thin() -> None:
    report = json.loads(buildable_unit_evidence_depth_status_to_json({"units": [{"unit_id": "u1", "signal_count": 2, "insight_count": 1, "distinct_source_count": 1}]}))

    assert report["units"][0]["status"] == "thin"
    assert report["units"][0]["missing_depth_reasons"] == ["source_diversity"]


def test_buildable_unit_evidence_depth_status_empty_input() -> None:
    report = json.loads(buildable_unit_evidence_depth_status_to_json({"units": []}))

    assert report["summary"]["unit_count"] == 0
    assert report["summary"]["status"] == "ready"
