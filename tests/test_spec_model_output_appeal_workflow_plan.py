from __future__ import annotations

import json

from max.spec.model_output_appeal_workflow_plan import generate_model_output_appeal_workflow_plan


def test_model_output_appeal_workflow_plan_includes_required_sections() -> None:
    plan = generate_model_output_appeal_workflow_plan({})

    assert set(plan) >= {
        "appeal_intake",
        "reviewer_roles",
        "evidence_requirements",
        "decision_slas",
        "escalation_paths",
        "audit_logging",
        "notification_steps",
        "evidence_references",
    }
    assert sorted(item["name"] for item in plan["reviewer_roles"]) == sorted(
        [
        "privacy reviewer verifies sensitive data handling",
        "model reviewer evaluates output evidence and rubric fit",
        "product reviewer confirms customer impact and remedy",
        ]
    )


def test_model_output_appeal_workflow_plan_uses_metadata_hints() -> None:
    plan = generate_model_output_appeal_workflow_plan(
        {
            "metadata": {
                "model_output_appeal_workflow": {
                    "reviewer_roles": ["trust reviewer"],
                    "decision_slas": ["24 hour critical dispute decision"],
                    "escalation_paths": ["legal escalation"],
                }
            },
            "evidence": {"signal_ids": ["appeal-1"]},
        }
    )

    assert plan["reviewer_roles"][0]["name"] == "trust reviewer"
    assert plan["decision_slas"][0]["name"] == "24 hour critical dispute decision"
    assert plan["escalation_paths"][0]["name"] == "legal escalation"
    assert plan == generate_model_output_appeal_workflow_plan(
        {
            "metadata": {
                "model_output_appeal_workflow": {
                    "reviewer_roles": ["trust reviewer"],
                    "decision_slas": ["24 hour critical dispute decision"],
                    "escalation_paths": ["legal escalation"],
                }
            },
            "evidence": {"signal_ids": ["appeal-1"]},
        }
    )
    assert json.loads(json.dumps(plan)) == plan
