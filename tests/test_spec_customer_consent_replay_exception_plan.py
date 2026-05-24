from __future__ import annotations

from max.spec import generate_customer_consent_replay_exception_plan


def test_customer_consent_replay_exception_plan_preserves_event_fields() -> None:
    plan = generate_customer_consent_replay_exception_plan(
        {
            "evidence": {"insight_ids": ["consent-gap"]},
            "metadata": {
                "customer_consent_replay_exception": {
                    "replay_events": [
                        {
                            "event": "marketing_opt_in_replay",
                            "customer_segment": "eu-trial-customers",
                            "owner": "privacy_ops",
                            "occurred_at": "2026-05-20T10:00:00Z",
                        }
                    ],
                    "validation": ["compare consent ledger before and after replay"],
                    "notifications": ["notify affected eu trial customers"],
                    "rollback": ["restore prior consent state"],
                }
            },
        }
    )

    assert plan["replay_events"][0]["name"] == "marketing_opt_in_replay"
    assert plan["replay_events"][0]["event"] == "marketing_opt_in_replay"
    assert plan["replay_events"][0]["customer_segment"] == "eu-trial-customers"
    assert plan["replay_events"][0]["owner"] == "privacy_ops"
    assert plan["replay_events"][0]["occurred_at"] == "2026-05-20T10:00:00Z"
    assert plan["validation_checks"][0]["evidence_reference_ids"] == ["EV1"]
    assert set(plan) >= {
        "replay_events",
        "affected_segments",
        "exception_reason",
        "validation_checks",
        "notification_plan",
        "audit_evidence",
        "expiry_workflow",
        "rollback_plan",
        "evidence_references",
    }


def test_customer_consent_replay_exception_plan_defaults_include_validation_and_notification() -> None:
    plan = generate_customer_consent_replay_exception_plan({})

    assert plan["validation_checks"]
    assert "pre/post consent state comparison" in plan["validation_checks"][0]["name"]
    assert plan["notification_plan"]
    assert "customer notification criteria" in plan["notification_plan"][0]["name"]
