from __future__ import annotations

from max.spec.customer_communication_plan import generate_customer_communication_plan


def test_customer_communication_plan_covers_required_sections() -> None:
    plan = generate_customer_communication_plan(
        {
            "project": {"title": "Billing Migration", "target_users": "admins"},
            "communication": {
                "change_type": "customer-impacting migration",
                "audiences": ["admins", "finance"],
                "channels": ["email", "webinar"],
                "escalation_paths": ["cs-manager"],
            },
            "execution": {"risks": ["downtime during migration"]},
            "evidence": {"signal_ids": ["cust-1"]},
        }
    )

    assert plan["kind"] == "max.customer_communication_plan"
    assert plan["summary"]["risk_level"] == "high"
    assert plan["summary"]["communication_cadence"] == "high-touch"
    assert plan["audiences"] == ["admins", "finance"]
    assert plan["channels"] == ["email", "webinar"]
    assert plan["audience_channel_matrix"][0] == {"audience": "admins", "channel": "email", "message_theme": "support path"}
    assert plan["rollback_messaging"] == ["prepare rollback notice", "confirm restored state and support path"]
    assert len(plan["timing"]) == 3
    assert plan["evidence"] == ["signal:cust-1"]


def test_customer_communication_plan_defaults_missing_fields() -> None:
    plan = generate_customer_communication_plan({})

    assert plan["summary"]["title"] == "Unknown"
    assert plan["summary"]["communication_cadence"] == "standard"
    assert plan["audiences"] == ["Unknown"]
    assert plan["escalation_paths"] == ["Unknown"]
    assert plan["blockers"] == ["missing owner", "missing audience", "missing approval path"]


def test_customer_communication_plan_is_deterministic() -> None:
    payload = {"communication": {"audiences": ["z", "a", "z"]}}

    assert generate_customer_communication_plan(payload) == generate_customer_communication_plan(payload)
    assert generate_customer_communication_plan(payload)["audiences"] == ["a", "z"]
