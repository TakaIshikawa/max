from __future__ import annotations

import json

from max.spec.synthetic_evaluation_disclosure_plan import (
    generate_synthetic_evaluation_disclosure_plan,
)


def test_synthetic_evaluation_disclosure_plan_covers_internal_disclosure() -> None:
    plan = generate_synthetic_evaluation_disclosure_plan(
        {
            "metadata": {
                "synthetic_evaluation_disclosure": {
                    "scopes": [{"dataset": "internal benchmark v2", "purpose": "regression testing"}],
                    "audience": ["internal reviewers"],
                }
            }
        }
    )

    assert plan["synthetic_data_scope"][0]["dataset"] == "internal benchmark v2"
    assert plan["disclosure_audience"][0]["name"] == "internal reviewers"


def test_synthetic_evaluation_disclosure_plan_covers_external_disclosure() -> None:
    plan = generate_synthetic_evaluation_disclosure_plan(
        {
            "metadata": {
                "synthetic_evaluation_disclosure": {
                    "synthetic_data_scope": [{"benchmark": "public eval report"}],
                    "audiences": ["customers and benchmark readers"],
                    "labels": ["label synthetic rows in appendix"],
                }
            }
        }
    )

    assert plan["synthetic_data_scope"][0]["benchmark"] == "public eval report"
    assert plan["labeling_requirements"][0]["name"] == "label synthetic rows in appendix"


def test_synthetic_evaluation_disclosure_plan_flags_unlabeled_examples() -> None:
    plan = generate_synthetic_evaluation_disclosure_plan(
        {"metadata": {"synthetic_evaluation_disclosure": {"unlabeled_synthetic_examples": True}}}
    )

    assert plan["risks"][0]["name"] == "unlabeled synthetic examples"
    assert plan["risks"][0]["severity"] == "high"


def test_synthetic_evaluation_disclosure_plan_includes_validation_evidence() -> None:
    plan = generate_synthetic_evaluation_disclosure_plan(
        {
            "metadata": {
                "synthetic_evaluation_disclosure": {
                    "validation_evidence": ["human review of 200 generated examples"]
                }
            }
        }
    )

    assert plan["validation_evidence"][0]["name"] == "human review of 200 generated examples"


def test_synthetic_evaluation_disclosure_plan_is_deterministic_and_preserves_metadata() -> None:
    payload = {
        "source": {"idea_id": "sed-1"},
        "metadata": {
            "synthetic_evaluation_disclosure": {
                "examples": [{"dataset": "z"}, {"dataset": "a"}, {"dataset": "a"}]
            }
        },
    }

    first = generate_synthetic_evaluation_disclosure_plan(payload)
    assert first == generate_synthetic_evaluation_disclosure_plan(payload)
    assert [row["name"] for row in first["synthetic_data_scope"]] == ["a", "z"]
    assert first["source"]["idea_id"] == "sed-1"
    assert json.loads(json.dumps(first)) == first
