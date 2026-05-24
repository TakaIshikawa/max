from __future__ import annotations

import json

from max.spec import generate_training_dataset_removal_plan


def test_training_dataset_removal_plan_covers_dataset_removal_workflow() -> None:
    plan = generate_training_dataset_removal_plan(
        _spec(
            "training_dataset_removal",
            {
                "datasets": [
                    {
                        "dataset": "legacy prompts",
                        "source": "training-lake",
                        "reason": "consent withdrawal",
                        "owner": "privacy_owner",
                        "due_at": "2026-06-01",
                    }
                ],
                "removal_triggers": ["consent withdrawal"],
                "downstream_impact": ["gpt-risk fine tune"],
                "removal_steps": ["quarantine shards and retrain"],
                "verification_plan": ["lineage query shows zero references"],
                "owner_matrix": ["privacy, data, model, and release owners"],
                "timeline": ["remove before next training run"],
                "rollback_plan": ["restore last approved model artifact"],
            },
        )
    )

    assert set(plan) >= {
        "datasets",
        "removal_triggers",
        "downstream_impact",
        "removal_steps",
        "verification_plan",
        "owner_matrix",
        "timeline",
        "rollback_plan",
        "evidence_references",
    }
    assert plan["datasets"][0]["name"] == "legacy prompts"
    assert plan["datasets"][0]["source"] == "training-lake"
    assert plan["datasets"][0]["reason"] == "consent withdrawal"
    assert plan["datasets"][0]["owner"] == "privacy_owner"
    assert plan["datasets"][0]["due_at"] == "2026-06-01"
    assert json.loads(json.dumps(plan)) == plan


def test_training_dataset_removal_plan_defaults_meaningful_workflow() -> None:
    plan = generate_training_dataset_removal_plan({})

    assert plan["schema_version"] == "max.spec.training_dataset_removal_plan.v1"
    assert plan["datasets"][0]["reason"] == "policy, consent, quality, or licensing removal trigger"
    assert plan["removal_steps"][0]["name"] == (
        "freeze affected training runs, quarantine dataset shards, rebuild derived features, "
        "and schedule retraining if needed"
    )
    assert plan["verification_plan"][0]["name"] == (
        "storage deletion receipt, lineage query, retraining manifest, and reviewer signoff"
    )


def _spec(key: str, hints: dict) -> dict:
    return {"metadata": {key: hints}, "evidence": {"signal_ids": ["tdr-1"]}}
