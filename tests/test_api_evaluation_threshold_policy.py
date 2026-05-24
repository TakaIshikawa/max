from __future__ import annotations

import json

from max.api.evaluation_threshold_policy import (
    KIND,
    SCHEMA_VERSION,
    evaluation_threshold_policy_to_json,
)


def test_evaluation_threshold_policy_to_json_normalizes_weights_and_validates() -> None:
    payload = {
        "schema_version": "max.evaluation_threshold_policy.v1",
        "kind": "max.evaluation_threshold_policy",
        "profile_policies": [
            {
                "id": "p2",
                "profile": "growth",
                "dimension": "value",
                "dimension_weights": {"market": 3, "risk": 1},
                "approve_threshold": 0.8,
                "revise_threshold": 0.5,
                "reject_threshold": 0.2,
            },
            {
                "id": "p1",
                "profile": "growth",
                "dimension": "risk",
                "dimension_weights": {"risk": 1},
                "approve_threshold": 0.4,
                "revise_threshold": 0.6,
                "reject_threshold": 0.2,
            },
        ],
    }

    output = evaluation_threshold_policy_to_json(payload)
    parsed = json.loads(output)

    assert parsed["schema_version"] == SCHEMA_VERSION
    assert parsed["kind"] == KIND
    assert parsed["summary"] == {"invalid_policy_count": 1, "policy_count": 2, "valid_policy_count": 1}
    assert [row["dimension"] for row in parsed["policies"]] == ["risk", "value"]
    assert parsed["policies"][1]["normalized_weights"] == {"market": 0.75, "risk": 0.25}
    assert parsed["invalid_policies"][0]["policy_id"] == "p1"
    assert output == evaluation_threshold_policy_to_json(payload)


def test_evaluation_threshold_policy_to_json_defaults_missing_optional_fields() -> None:
    parsed = json.loads(evaluation_threshold_policy_to_json({"policies": [{}]}))

    assert parsed["policies"][0]["policy_id"] == "policy-1"
    assert parsed["policies"][0]["profile"] == "default"
    assert parsed["policies"][0]["dimension"] == "overall"
    assert parsed["policies"][0]["thresholds_valid"] is True
