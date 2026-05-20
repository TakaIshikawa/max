from __future__ import annotations

import json

from max.spec import generate_data_processing_impact_review_plan


def test_data_processing_impact_review_plan_uses_hints() -> None:
    plan = generate_data_processing_impact_review_plan(
        _spec(
            {
                "data_categories": ["payment data", "account data"],
                "processing_purposes": ["billing"],
                "affected_systems": ["ledger"],
                "policy_basis": [{"name": "DPA basis", "owner": "privacy"}],
                "residual_risks": ["retention drift"],
                "mitigations": ["retention guardrail"],
                "validation_checks": ["privacy signoff"],
            }
        )
    )

    assert [item["name"] for item in plan["data_categories"]] == ["account data", "payment data"]
    assert plan["basis_review"][0]["owner"] == "privacy"
    assert plan["validation_checks"][0]["evidence_reference_ids"] == ["EV1"]
    assert json.loads(json.dumps(plan)) == plan


def test_data_processing_impact_review_plan_defaults_sparse_input() -> None:
    plan = generate_data_processing_impact_review_plan({})

    assert plan["data_categories"][0]["name"] == "account data"
    assert plan["processing_purposes"][0]["name"] == "Support primary workflow"
    assert plan["affected_systems"][0]["name"] == "application service"
    assert json.loads(json.dumps(plan)) == plan


def _spec(hints: dict) -> dict:
    return {"metadata": {"data_processing_impact_review": hints}, "evidence": {"source_idea_ids": ["idea-1"]}}
