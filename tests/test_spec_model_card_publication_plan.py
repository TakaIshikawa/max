from __future__ import annotations

import json

from max.spec.model_card_publication_plan import generate_model_card_publication_plan


def test_model_card_publication_plan_includes_required_publication_sections() -> None:
    plan = generate_model_card_publication_plan(
        {
            "evidence": {"signal_ids": ["model-card"]},
            "metadata": {
                "model_card_publication": {
                    "model_identity": [{"model": "risk-router", "version": "2026.05"}],
                    "intended_users": ["support operations analysts"],
                    "limitations": ["not approved for automated account closure"],
                    "evaluation_results": [{"metric": "precision", "score": "0.94", "threshold": "0.90"}],
                    "data_provenance": [{"dataset": "support tickets", "source": "consented customer support data"}],
                    "safety": ["human review required for high-impact recommendations"],
                    "owner_approvals": [{"role": "safety_owner", "status": "approved"}],
                    "post_publication_updates": [{"trigger": "new model version"}],
                }
            },
        }
    )

    assert plan["schema_version"] == "max.spec.model_card_publication_plan.v1"
    assert plan["model_identity"][0]["name"] == "risk-router"
    assert plan["model_identity"][0]["version"] == "2026.05"
    assert plan["intended_use"][0]["name"] == "support operations analysts"
    assert plan["evaluation_results"][0]["metric"] == "precision"
    assert plan["data_provenance_summary"][0]["dataset"] == "support tickets"
    assert plan["safety_considerations"][0]["name"] == "human review required for high-impact recommendations"
    assert plan["publication_risk_flags"][0]["severity"] == "low"
    assert json.loads(json.dumps(plan)) == plan


def test_model_card_publication_plan_flags_missing_evaluation_and_safety_sections() -> None:
    plan = generate_model_card_publication_plan(
        {"metadata": {"model_card_publication": {"model": [{"model": "classifier", "version": "v2"}]}}}
    )

    assert [flag["name"] for flag in plan["publication_risk_flags"]] == [
        "missing evaluation results",
        "missing safety considerations",
    ]
    assert [flag["severity"] for flag in plan["publication_risk_flags"]] == ["high", "high"]
    assert plan["summary"]["publication_blocker_count"] == 2


def test_model_card_publication_plan_defaults_publication_and_update_tasks() -> None:
    plan = generate_model_card_publication_plan({})

    assert plan["model_identity"][0]["version"] == "to be confirmed"
    assert "evaluations" in plan["publication_checklist"][0]["name"]
    assert "version changes" in plan["post_publication_updates"][0]["name"]
