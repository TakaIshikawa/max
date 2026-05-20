from __future__ import annotations

import json

from max.spec import generate_webhook_consumer_migration_plan


def test_webhook_consumer_migration_plan_sorts_consumers() -> None:
    plan = generate_webhook_consumer_migration_plan(
        _spec(
            "webhook_consumer_migration",
            {
                "consumer_inventory": [
                    {"name": "analytics sink", "severity": "low"},
                    {"name": "billing sync", "severity": "critical", "deadline_status": "ready"},
                    {"name": "crm bridge", "severity": "high", "deadline_status": "missing"},
                    {"name": "billing sync", "severity": "critical"},
                ],
                "endpoint_changes": ["v2 endpoint"],
                "signing_secret_actions": ["dual secret validation"],
                "retry_backfill_strategy": ["replay missed deliveries"],
                "compatibility_window": ["30 days"],
                "communications": ["partner email"],
                "validation_checks": ["signature smoke test"],
            },
        )
    )

    assert [item["name"] for item in plan["consumer_inventory"]] == [
        "billing sync",
        "crm bridge",
        "analytics sink",
    ]
    assert plan["endpoint_changes"][0]["name"] == "v2 endpoint"
    assert plan["validation_checks"][0]["evidence_reference_ids"] == ["EV1"]
    assert json.loads(json.dumps(plan)) == plan


def test_webhook_consumer_migration_plan_defaults_sparse_input() -> None:
    plan = generate_webhook_consumer_migration_plan({})

    assert plan["consumer_inventory"][0]["name"] == "default webhook consumer"
    assert set(plan) >= {
        "endpoint_changes",
        "signing_secret_actions",
        "retry_backfill_strategy",
        "compatibility_window",
        "communications",
        "source",
        "evidence_references",
    }
    assert json.loads(json.dumps(plan)) == plan


def _spec(key: str, hints: dict) -> dict:
    return {"metadata": {key: hints}, "evidence": {"source_idea_ids": ["idea-1"]}}
