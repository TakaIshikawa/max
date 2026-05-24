from __future__ import annotations

import json

from max.spec.evaluation_rubric_change_approval_plan import (
    generate_evaluation_rubric_change_approval_plan,
)


def test_evaluation_rubric_change_approval_plan_captures_weight_changes() -> None:
    plan = generate_evaluation_rubric_change_approval_plan(
        {
            "source": {"idea_id": "rubric-1", "domain": "evaluation"},
            "metadata": {
                "evaluation_rubric_change_approval": {
                    "changes": [
                        {
                            "dimension": "factuality",
                            "old_weight": "30%",
                            "new_weight": "40%",
                            "owner": "eval lead",
                        }
                    ],
                    "profiles": [{"profile": "enterprise support"}],
                    "validation_evidence": ["backtest against adjudicated sample"],
                    "reviewers": [{"role": "responsible AI reviewer", "required": "yes"}],
                }
            },
            "evidence": {"signal_ids": ["rubric-sig"]},
        }
    )

    change = plan["change_summary"][0]
    assert change["name"] == "factuality"
    assert change["old_weight"] == "30%"
    assert change["new_weight"] == "40%"
    assert plan["impacted_profiles"][0]["profile"] == "enterprise support"
    assert plan["validation_evidence"][0]["name"] == "backtest against adjudicated sample"
    assert plan["reviewer_roles"][0]["role"] == "responsible AI reviewer"
    assert plan["source"]["idea_id"] == "rubric-1"
    assert plan["evidence_references"][0]["reference"] == "signal:rubric-sig"
    assert plan["change_summary"][0]["evidence_reference_ids"] == ["EV1"]


def test_evaluation_rubric_change_approval_plan_captures_threshold_changes() -> None:
    plan = generate_evaluation_rubric_change_approval_plan(
        {
            "metadata": {
                "evaluation_rubric_change_approval": {
                    "changed_dimensions": [
                        {
                            "dimension": "toxicity",
                            "old_threshold": "<= 0.02",
                            "new_threshold": "<= 0.01",
                        }
                    ],
                    "release_gate": ["approval, regression comparison, and rollback readiness"],
                }
            }
        }
    )

    assert plan["change_summary"][0]["old_threshold"] == "<= 0.02"
    assert plan["change_summary"][0]["new_threshold"] == "<= 0.01"
    assert "approval" in plan["acceptance_criteria"][0]["name"]
    assert "regression comparison" in plan["acceptance_criteria"][0]["name"]
    assert "rollback readiness" in plan["acceptance_criteria"][0]["name"]


def test_evaluation_rubric_change_approval_plan_flags_missing_validation_evidence() -> None:
    plan = generate_evaluation_rubric_change_approval_plan(
        {"metadata": {"evaluation_rubric_change_approval": {"changes": [{"dimension": "helpfulness"}]}}}
    )

    assert plan["risks"][0]["name"] == "missing validation evidence"
    assert plan["risks"][0]["severity"] == "high"


def test_evaluation_rubric_change_approval_plan_includes_rollback_steps() -> None:
    plan = generate_evaluation_rubric_change_approval_plan(
        {
            "metadata": {
                "evaluation_rubric_change_approval": {
                    "rollback_steps": ["restore rubric v12", "recompute queued recommendations"],
                }
            }
        }
    )

    assert [row["name"] for row in plan["rollback_plan"]] == [
        "recompute queued recommendations",
        "restore rubric v12",
    ]


def test_evaluation_rubric_change_approval_plan_is_deterministic() -> None:
    payload = {
        "metadata": {
            "evaluation_rubric_change_approval": {
                "changes": [{"dimension": "z"}, {"dimension": "a"}, {"dimension": "a"}],
                "validation": ["comparison"],
            }
        }
    }

    first = generate_evaluation_rubric_change_approval_plan(payload)
    assert first == generate_evaluation_rubric_change_approval_plan(payload)
    assert [row["name"] for row in first["change_summary"]] == ["a", "z"]
    assert json.loads(json.dumps(first)) == first


def test_evaluation_rubric_change_approval_plan_defaults_are_meaningful() -> None:
    plan = generate_evaluation_rubric_change_approval_plan({})

    assert plan["schema_version"] == "max.spec.evaluation_rubric_change_approval_plan.v1"
    assert set(plan) >= {
        "change_summary",
        "impacted_profiles",
        "validation_evidence",
        "reviewer_roles",
        "rollback_plan",
        "acceptance_criteria",
        "risks",
    }
    assert plan["acceptance_criteria"][0]["name"] == (
        "approval captured, regression comparison accepted, and rollback readiness confirmed"
    )
