from __future__ import annotations

import json

from max.spec import generate_release_risk_acceptance_plan as exported_generator
from max.spec.release_risk_acceptance_plan import KIND, SCHEMA_VERSION, generate_release_risk_acceptance_plan


def test_release_risk_acceptance_plan_normalizes_hints_and_execution_risks() -> None:
    plan = generate_release_risk_acceptance_plan(
        {
            "execution": {"risks": ["dependency outage"]},
            "metadata": {
                "release_risk_acceptance": {
                    "accepted_risks": [{"risk": "margin exposure", "severity": "high", "owner": "finance", "rationale": "short window"}],
                    "mitigations": [{"name": "daily margin review", "owner": "finance"}],
                    "approvers": ["vp_product"],
                    "review_cadence": "daily",
                }
            },
        }
    )

    assert plan["schema_version"] == SCHEMA_VERSION
    assert plan["kind"] == KIND
    assert plan["accepted_risks"][0]["risk"] == "margin exposure"
    assert plan["accepted_risks"][0]["severity"] == "high"
    assert plan["mitigation_actions"][0]["owner"] == "finance"
    assert plan["review_cadence"]["cadence"] == "daily"
    assert exported_generator({})["kind"] == KIND


def test_release_risk_acceptance_plan_defaults_are_stable_and_json_serializable() -> None:
    first = generate_release_risk_acceptance_plan({})
    second = generate_release_risk_acceptance_plan({})

    assert first == second
    assert first["accepted_risks"][0]["risk"] == "release risk review pending"
    assert [item["role"] for item in first["approver_signoffs"]] == ["engineering_owner", "product_owner", "release_manager"]
    assert json.loads(json.dumps(first))["kind"] == KIND
