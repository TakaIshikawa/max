from __future__ import annotations

import json

from max.spec import generate_release_communications_readiness_plan


def test_release_communications_readiness_plan_uses_hints() -> None:
    plan = generate_release_communications_readiness_plan(
        _spec(
            "release_communications_readiness",
            {
                "audiences": ["admins", "end users", "admins"],
                "message_variants": [
                    {"name": "admin copy"},
                    {"name": "user copy"},
                    {"name": "admin copy"},
                ],
                "channels": ["email", "status page", "email"],
                "approval_owners": ["legal"],
                "timing_gates": ["release gate"],
                "localization_accessibility_needs": ["WCAG review"],
                "validation_checks": ["send dry run"],
            },
        )
    )

    assert [item["name"] for item in plan["audiences"]] == ["admins", "end users"]
    assert [item["name"] for item in plan["message_variants"]] == ["admin copy", "user copy"]
    assert [item["name"] for item in plan["channels"]] == ["email", "status page"]
    assert plan["validation_checks"][0]["evidence_reference_ids"] == ["EV1"]
    assert json.loads(json.dumps(plan)) == plan


def test_release_communications_readiness_plan_defaults_sparse_input() -> None:
    plan = generate_release_communications_readiness_plan({})

    assert plan["audiences"][0]["name"] == "primary user"
    assert plan["message_variants"][0]["name"] == "primary release message"
    assert set(plan) >= {
        "channels",
        "approval_owners",
        "timing_gates",
        "localization_accessibility_needs",
        "source",
        "evidence_references",
    }
    assert json.loads(json.dumps(plan)) == plan


def _spec(key: str, hints: dict) -> dict:
    return {"metadata": {key: hints}, "evidence": {"source_idea_ids": ["idea-1"]}}
