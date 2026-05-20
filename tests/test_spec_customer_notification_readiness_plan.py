from __future__ import annotations

import json

from max.spec import generate_customer_notification_readiness_plan


def test_customer_notification_readiness_plan_uses_hints() -> None:
    plan = generate_customer_notification_readiness_plan(
        _spec(
            {
                "audience_segments": ["admins"],
                "notification_triggers": ["incident resolved"],
                "channels": ["email", "portal"],
                "approval_gates": [{"name": "legal approval", "owner": "legal"}],
                "send_timing": ["after RCA"],
                "localization_needs": ["ja-JP"],
                "validation_checks": ["template preview"],
            }
        )
    )

    assert plan["audience_segments"][0]["name"] == "admins"
    assert [item["name"] for item in plan["channels"]] == ["email", "portal"]
    assert plan["approval_gates"][0]["owner"] == "legal"
    assert plan["validation_checks"][0]["evidence_reference_ids"] == ["EV1"]
    assert json.loads(json.dumps(plan)) == plan


def test_customer_notification_readiness_plan_defaults_sparse_input() -> None:
    plan = generate_customer_notification_readiness_plan({})

    assert plan["audience_segments"][0]["name"] == "primary user"
    assert plan["localization_needs"][0]["name"] == "default locale"
    assert json.loads(json.dumps(plan)) == plan


def _spec(hints: dict) -> dict:
    return {"metadata": {"customer_notification_readiness": hints}, "evidence": {"insight_ids": ["ins-1"]}}
