from __future__ import annotations

import json

from max.spec.inference_cache_purge_verification_plan import (
    generate_inference_cache_purge_verification_plan,
)


def test_inference_cache_purge_verification_plan_accepts_aliases() -> None:
    plan = generate_inference_cache_purge_verification_plan(
        {
            "metadata": {
                "inference_cache_purge_verification": {
                    "cache_entries": [
                        {"cache_key": "tenant-a/prompts", "store": "redis", "region": "us-east"}
                    ],
                    "triggers": ["customer deletion"],
                    "customer_scope": ["tenant-a prompts and embeddings"],
                    "evidence": ["cache miss sample"],
                    "exceptions": ["edge replica drains within 24h"],
                    "rollback_controls": ["block stale replay"],
                    "approvals": ["privacy owner signoff"],
                }
            },
            "evidence": {"signal_ids": ["icp-1"]},
        }
    )

    assert plan["schema_version"] == "max.spec.inference_cache_purge_verification_plan.v1"
    assert plan["cache_inventories"][0]["name"] == "tenant-a/prompts"
    assert plan["cache_inventories"][0]["store"] == "redis"
    assert plan["purge_triggers"][0]["name"] == "customer deletion"
    assert plan["data_scope"][0]["name"] == "tenant-a prompts and embeddings"
    assert plan["verification_evidence"][0]["name"] == "cache miss sample"
    assert plan["residual_risk_exceptions"][0]["name"] == "edge replica drains within 24h"
    assert plan["replay_safeguards"][0]["name"] == "block stale replay"
    assert plan["approval_gates"][0]["name"] == "privacy owner signoff"
    assert json.loads(json.dumps(plan)) == plan


def test_inference_cache_purge_verification_plan_defaults_are_meaningful() -> None:
    plan = generate_inference_cache_purge_verification_plan({})

    assert set(plan) >= {
        "schema_version",
        "kind",
        "source",
        "summary",
        "cache_inventories",
        "purge_triggers",
        "data_scope",
        "verification_evidence",
        "residual_risk_exceptions",
        "replay_safeguards",
        "approval_gates",
        "evidence_references",
    }
    assert plan["cache_inventories"][0]["id"] == "ICP1"
    assert plan["cache_inventories"][0]["owner"] == "ml_platform_owner"
    assert plan["purge_triggers"][0]["owner"] == "ml_platform_owner"
