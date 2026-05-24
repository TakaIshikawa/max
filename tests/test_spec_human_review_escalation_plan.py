from __future__ import annotations

import json

from max.spec.human_review_escalation_plan import generate_human_review_escalation_plan


def test_human_review_escalation_plan_covers_queue_sla_decisions_and_notifications() -> None:
    plan = generate_human_review_escalation_plan(
        _spec(
            {
                "triggers": [
                    {"trigger": "brand safety ambiguity", "risk_level": "medium"},
                    {"condition": "regulated financial advice", "risk": "critical"},
                    {"scenario": "low confidence rewrite", "severity": "low"},
                ],
                "reviewer_queue": [{"queue": "policy-review", "owner": "trust_safety"}],
                "sla": [{"target": "4 business hours"}],
                "decision_outcomes": ["approve with edits"],
                "override_logging": ["log override reason and approver"],
                "notification_path": [{"channel": "#human-review", "recipient": "workflow owner"}],
            }
        )
    )

    assert plan["schema_version"] == "max.spec.human_review_escalation_plan.v1"
    assert [item["name"] for item in plan["escalation_triggers"]] == [
        "regulated financial advice",
        "brand safety ambiguity",
        "low confidence rewrite",
    ]
    assert plan["escalation_triggers"][0]["risk_level"] == "critical"
    assert plan["reviewer_queue"][0]["name"] == "policy-review"
    assert plan["sla"][0]["name"] == "4 business hours"
    assert plan["decision_outcomes"][0]["name"] == "approve with edits"
    assert plan["override_logging"][0]["name"] == "log override reason and approver"
    assert plan["notification_path"][0]["channel"] == "#human-review"
    assert json.loads(json.dumps(plan)) == plan


def test_human_review_escalation_plan_defaults_missing_sla_to_review_required() -> None:
    plan = generate_human_review_escalation_plan(_spec({"conditions": [{"condition": "novel abuse pattern"}]}))

    assert plan["escalation_triggers"][0]["name"] == "novel abuse pattern"
    assert plan["escalation_triggers"][0]["risk_level"] == "high"
    assert plan["sla"][0]["name"] == "review-required"
    assert set(plan) >= {
        "escalation_triggers",
        "reviewer_queue",
        "sla",
        "decision_outcomes",
        "override_logging",
        "notification_path",
        "evidence_references",
    }


def _spec(hints: dict) -> dict:
    return {"metadata": {"human_review_escalation": hints}, "evidence": {"signal_ids": ["hr-1"]}}
