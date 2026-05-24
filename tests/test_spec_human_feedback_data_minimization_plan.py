from __future__ import annotations

import json

from max.spec.human_feedback_data_minimization_plan import (
    generate_human_feedback_data_minimization_plan,
)


def test_human_feedback_data_minimization_plan_maps_sensitive_fields() -> None:
    plan = generate_human_feedback_data_minimization_plan(
        {
            "metadata": {
                "human_feedback_data_minimization": {
                    "feedback_fields": [
                        {"field": "reviewer_email", "action": "redact", "classification": "personal data"},
                        {"field": "rubric_score", "action": "keep", "purpose": "learning"},
                    ],
                    "redactions": ["remove customer identifiers from free text"],
                }
            }
        }
    )

    by_name = {row["name"]: row for row in plan["feedback_fields"]}
    assert by_name["reviewer_email"]["action"] == "redact"
    assert by_name["rubric_score"]["action"] == "keep"
    assert plan["redaction_rules"][0]["name"] == "remove customer identifiers from free text"


def test_human_feedback_data_minimization_plan_supports_aggregation_only_mode() -> None:
    plan = generate_human_feedback_data_minimization_plan(
        {
            "metadata": {
                "human_feedback_data_minimization": {
                    "aggregation": ["store only weekly rubric aggregates"],
                    "fields": [{"field": "raw_comment", "action": "delete"}],
                }
            }
        }
    )

    assert plan["aggregation_strategy"][0]["name"] == "store only weekly rubric aggregates"
    assert plan["feedback_fields"][0]["action"] == "delete"


def test_human_feedback_data_minimization_plan_represents_reviewer_identity() -> None:
    plan = generate_human_feedback_data_minimization_plan(
        {
            "metadata": {
                "human_feedback_data_minimization": {
                    "reviewer_identity": ["hash reviewer id for audit lookup"],
                    "fields": [{"field": "reviewer_identity", "action": "hash"}],
                }
            }
        }
    )

    assert plan["reviewer_identity_handling"][0]["name"] == "hash reviewer id for audit lookup"
    assert plan["risks"][0]["name"] == "reviewer identity exposure"


def test_human_feedback_data_minimization_plan_defaults_and_acceptance() -> None:
    plan = generate_human_feedback_data_minimization_plan({})

    assert plan["schema_version"] == "max.spec.human_feedback_data_minimization_plan.v1"
    assert plan["feedback_fields"][0]["field"] == "review_score, rationale"
    assert "minimization verification" in plan["acceptance_criteria"][0]["name"]
    assert "audit evidence" in plan["acceptance_criteria"][0]["name"]


def test_human_feedback_data_minimization_plan_is_deterministic_and_preserves_metadata() -> None:
    payload = {
        "source": {"idea_id": "hfm-1"},
        "metadata": {
            "human_feedback_data_minimization": {
                "fields": [{"field": "z"}, {"field": "a"}, {"field": "a"}],
                "evidence": ["field inventory export"],
            }
        },
        "evidence": {"source_idea_ids": ["hfm-src"]},
    }

    first = generate_human_feedback_data_minimization_plan(payload)
    assert first == generate_human_feedback_data_minimization_plan(payload)
    assert [row["name"] for row in first["feedback_fields"]] == ["a", "z"]
    assert first["source"]["idea_id"] == "hfm-1"
    assert json.loads(json.dumps(first)) == first
