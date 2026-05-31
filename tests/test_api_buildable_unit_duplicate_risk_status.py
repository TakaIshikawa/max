from __future__ import annotations

import json

from max.api.buildable_unit_duplicate_risk_status import buildable_unit_duplicate_risk_status_to_json


def test_buildable_unit_duplicate_risk_status_no_duplicates() -> None:
    parsed = json.loads(buildable_unit_duplicate_risk_status_to_json({"clusters": []}))

    assert parsed["summary"]["status"] == "healthy"
    assert parsed["duplicate_clusters"] == []


def test_buildable_unit_duplicate_risk_status_clustered_duplicates() -> None:
    parsed = json.loads(buildable_unit_duplicate_risk_status_to_json({"clusters": [{"unit_ids": ["u2", "u1"], "similarity_score": 0.95, "representative_title": "Checkout"}]}))

    assert parsed["summary"]["status"] == "critical"
    assert parsed["duplicate_clusters"][0]["unit_ids"] == ["u1", "u2"]


def test_buildable_unit_duplicate_risk_status_boundary_thresholds() -> None:
    parsed = json.loads(buildable_unit_duplicate_risk_status_to_json({"warning_threshold": 0.8, "critical_threshold": 0.9, "clusters": [{"unit_ids": ["a", "b"], "score": 0.8}, {"unit_ids": ["c", "d"], "score": 0.9}]}))

    assert [row["status"] for row in parsed["duplicate_clusters"]] == ["critical", "warning"]


def test_buildable_unit_duplicate_risk_status_stable_ordering() -> None:
    parsed = json.loads(buildable_unit_duplicate_risk_status_to_json({"clusters": [{"unit_ids": ["z", "a"], "score": 0.85, "title": "Zed"}, {"unit_ids": ["b", "c"], "score": 0.85, "title": "Alpha"}]}))

    assert [row["representative_title"] for row in parsed["duplicate_clusters"]] == ["Alpha", "Zed"]
