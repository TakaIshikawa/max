from __future__ import annotations

import json

from max.spec.fine_tuning_job_cancellation_plan import generate_fine_tuning_job_cancellation_plan


def test_fine_tuning_job_cancellation_plan_covers_custom_cancellation_controls() -> None:
    plan = generate_fine_tuning_job_cancellation_plan(
        _spec(
            {
                "jobs": [
                    {
                        "provider": "openai",
                        "job_id": "ftjob-123",
                        "model": "base-model",
                        "owner": "mlops",
                    }
                ],
                "triggers": [
                    {"trigger": "bad training shard", "severity": "high"},
                    {"condition": "spend above forecast", "threshold": "$500"},
                ],
                "rollback_steps": ["restore production route to previous model"],
                "checkpoint_disposition": [
                    {"checkpoint_id": "ckpt-9", "disposition": "quarantine"}
                ],
                "dataset_cleanup": [{"dataset": "fine-tune-v7", "location": "staging bucket"}],
                "cost_cap": [{"cost_cap": "$500", "currency": "USD"}],
                "stakeholder_notification": [
                    {"channel": "#ml-incidents", "recipient": "model owner"}
                ],
                "post_cancel_validation": ["provider reports cancelled"],
            }
        )
    )

    assert plan["schema_version"] == "max.spec.fine_tuning_job_cancellation_plan.v1"
    assert plan["job_identifiers"][0]["provider"] == "openai"
    assert plan["job_identifiers"][0]["job_id"] == "ftjob-123"
    assert [item["name"] for item in plan["cancellation_triggers"]] == [
        "bad training shard",
        "spend above forecast",
    ]
    assert plan["checkpoint_handling"][0]["disposition"] == "quarantine"
    assert plan["dataset_cleanup"][0]["dataset"] == "fine-tune-v7"
    assert plan["cost_controls"][0]["cost_cap"] == "$500"
    assert plan["stakeholder_notification"][0]["channel"] == "#ml-incidents"
    assert plan["blockers"] == []
    assert json.loads(json.dumps(plan)) == plan


def test_fine_tuning_job_cancellation_plan_defaults_and_blocks_missing_identifiers() -> None:
    plan = generate_fine_tuning_job_cancellation_plan(_spec({"conditions": ["quality regression"]}))

    assert plan["cancellation_triggers"][0]["name"] == "quality regression"
    assert plan["job_identifiers"][0]["provider"] == "provider-required"
    assert plan["job_identifiers"][0]["job_id"] == "job-id-required"
    assert [item["name"] for item in plan["blockers"]] == [
        "missing provider identifier",
        "missing fine-tuning job identifier",
    ]
    assert set(plan) >= {
        "rollback_steps",
        "checkpoint_handling",
        "dataset_cleanup",
        "cost_controls",
        "stakeholder_notification",
        "post_cancel_validation",
    }


def _spec(hints: dict) -> dict:
    return {
        "metadata": {"fine_tuning_job_cancellation": hints},
        "evidence": {"signal_ids": ["ft-1"]},
    }
