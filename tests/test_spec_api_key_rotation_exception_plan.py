from __future__ import annotations

import json

from max.spec import generate_api_key_rotation_exception_plan


def test_api_key_rotation_exception_plan_covers_high_risk_exception_controls() -> None:
    plan = generate_api_key_rotation_exception_plan(
        _spec(
            {
                "exceptions": [
                    {"scope": "CRM adapter", "owner": "integrations", "risk_level": "critical", "expiry": "2026-06-01"},
                    {"provider": "LLM Co", "risk": "low", "expiration": "2026-07-01"},
                ],
                "justification": ["vendor rotation window"],
                "compensating_controls": ["scoped key and usage alert"],
                "expiry_review": ["weekly exception review"],
                "rollback": ["revoke key and rotate"],
                "approval_criteria": ["security approval"],
                "verification_evidence": ["rotation ticket"],
            }
        )
    )

    assert plan["schema_version"] == "max.spec.api_key_rotation_exception_plan.v1"
    assert [item["name"] for item in plan["exception_scope"]] == ["CRM adapter", "LLM Co"]
    assert plan["exception_scope"][0]["risk_level"] == "critical"
    assert plan["exception_scope"][0]["expiry"] == "2026-06-01"
    assert plan["compensating_controls"][0]["name"] == "scoped key and usage alert"
    assert set(plan) >= {"justification", "expiry_review", "rollback", "approval_criteria", "verification_evidence"}
    assert json.loads(json.dumps(plan)) == plan


def test_api_key_rotation_exception_plan_defaults_expiry_risk_and_section_order() -> None:
    plan = generate_api_key_rotation_exception_plan(_spec({"adapters": [{"adapter": "Billing", "risk": "unknown"}]}))

    assert plan["exception_scope"][0]["name"] == "Billing"
    assert plan["exception_scope"][0]["risk_level"] == "high"
    assert plan["exception_scope"][0]["expiry"] == "30 days"
    assert list(plan) == [
        "schema_version",
        "kind",
        "source",
        "summary",
        "exception_scope",
        "justification",
        "compensating_controls",
        "expiry_review",
        "rollback",
        "approval_criteria",
        "verification_evidence",
        "evidence_references",
    ]


def _spec(hints: dict) -> dict:
    return {"metadata": {"api_key_rotation_exception": hints}, "evidence": {"signal_ids": ["ak-1"]}}
