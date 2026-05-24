from __future__ import annotations

import json

from max.spec import generate_external_model_provider_exception_plan


def test_external_model_provider_exception_plan_covers_controls_and_gates() -> None:
    plan = generate_external_model_provider_exception_plan(
        _spec(
            "external_model_provider_exception",
            {
                "vendors": [
                    {"vendor": "ModelCo", "model": "reasoner", "purpose": "support triage"}
                ],
                "rationale": ["capability gap until approved provider catches up"],
                "shared_data": ["redacted support transcript"],
                "contractual_controls": ["no-training addendum"],
                "security_review": ["SOC 2 and logging review"],
                "budget_impact": ["daily spend cap"],
                "fallback_provider": ["approved internal model"],
                "approvals": ["legal and privacy signoff"],
            },
        )
    )

    assert set(plan) >= {
        "providers",
        "exception_rationale",
        "data_sharing_scope",
        "contractual_controls",
        "security_review",
        "budget_impact",
        "fallback_plan",
        "approval_gates",
        "evidence_references",
    }
    assert plan["providers"][0]["name"] == "ModelCo"
    assert plan["providers"][0]["vendor"] == "ModelCo"
    assert plan["data_sharing_scope"][0]["name"] == "redacted support transcript"
    assert plan["approval_gates"][0]["name"] == "legal and privacy signoff"
    assert json.loads(json.dumps(plan)) == plan


def test_external_model_provider_exception_plan_defaults_provider_review() -> None:
    plan = generate_external_model_provider_exception_plan({})

    assert plan["schema_version"] == "max.spec.external_model_provider_exception_plan.v1"
    assert plan["providers"][0]["name"] == "external model provider"
    assert plan["contractual_controls"][0]["name"] == (
        "DPA, subprocessors, no-training commitment, retention limits, audit rights, "
        "and termination assistance"
    )
    assert plan["security_review"][0]["owner"] == "security_owner"


def _spec(key: str, hints: dict) -> dict:
    return {"metadata": {key: hints}, "evidence": {"signal_ids": ["emp-1"]}}
