from __future__ import annotations

import json

from max.api.retrospective_learning_status import retrospective_learning_status_to_json


def test_retrospective_learning_status_normalizes_adjustments_and_confidence() -> None:
    parsed = json.loads(
        retrospective_learning_status_to_json(
            {
                "min_confidence": 0.75,
                "min_sample_size": 20,
                "adjustments": [
                    {"id": "small", "profile": "sales", "dimension": "freshness", "delta": "0.1", "confidence": 0.8, "sample_size": 10, "approved": True},
                    {"id": "applied", "profile": "sales", "dimension": "quality", "weight_delta": -0.4, "confidence": 0.9, "sample_size": 30, "approved": "yes"},
                    {"id": "rejected", "profile": "support", "dimension": "risk", "weight_delta": 0.2, "approved": False},
                ],
            }
        )
    )

    assert [row["id"] for row in parsed["applied_adjustments"]] == ["applied"]
    assert [row["id"] for row in parsed["rejected_adjustments"]] == ["rejected"]
    assert any(row["id"] == "small" and "insufficient_sample_size" in row["reasons"] for row in parsed["pending_reviews"])


def test_retrospective_learning_status_extracts_pending_reviews_for_missing_inputs() -> None:
    parsed = json.loads(retrospective_learning_status_to_json({"scoring_weight_adjustments": [{"dimension": "fit", "confidence": 0.4}]}))

    assert parsed["pending_reviews"][0]["reasons"] == ["missing_approval", "low_confidence", "insufficient_sample_size"]
    assert parsed["profile_impact"][0]["profile"] == "unknown-profile"


def test_retrospective_learning_status_runs_metadata_and_schema() -> None:
    parsed = json.loads(
        retrospective_learning_status_to_json(
            {"schema_version": "source.v1", "kind": "source.kind", "runs": [{"id": "r1", "sample_size": "3"}]},
            as_of="2026-05-21T00:00:00Z",
        )
    )

    assert parsed["learning_runs"] == [{"completed_at": None, "run_id": "r1", "sample_size": 3, "status": "unknown"}]
    assert set(parsed) == {"schema_version", "kind", "summary", "learning_runs", "applied_adjustments", "rejected_adjustments", "pending_reviews", "profile_impact", "metadata"}
    assert parsed["metadata"]["source_kind"] == "source.kind"
