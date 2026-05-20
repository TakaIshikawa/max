from __future__ import annotations

import json

from max.spec import generate_schema_compatibility_review_plan


def test_schema_compatibility_review_plan_uses_hints() -> None:
    plan = generate_schema_compatibility_review_plan(
        _spec(
            "schema_compatibility_review",
            {
                "producers": ["orders", "billing", "orders"],
                "consumers": ["warehouse", "crm"],
                "compatibility_risks": [
                    {"name": "enum removal", "severity": "high", "status": "overdue"},
                    {"name": "optional field", "severity": "low"},
                    {"name": "enum removal", "severity": "high"},
                ],
                "migration_backfill_work": ["backfill version column"],
                "contract_tests": ["consumer pact"],
                "version_windows": ["v1/v2 overlap"],
                "owner_approvals": ["schema owner signoff"],
                "communications": ["developer notice"],
                "validation_checks": ["contract suite"],
            },
        )
    )

    assert [item["name"] for item in plan["producers"]] == ["billing", "orders"]
    assert [item["name"] for item in plan["compatibility_risks"]] == [
        "enum removal",
        "optional field",
    ]
    assert plan["validation_checks"][0]["evidence_reference_ids"] == ["EV1"]
    assert json.loads(json.dumps(plan)) == plan


def test_schema_compatibility_review_plan_defaults_sparse_input() -> None:
    plan = generate_schema_compatibility_review_plan({})

    assert plan["producers"][0]["name"] == "producer service"
    assert plan["consumers"][0]["name"] == "primary user"
    assert set(plan) >= {
        "migration_backfill_work",
        "contract_tests",
        "version_windows",
        "owner_approvals",
        "communications",
        "source",
        "evidence_references",
    }
    assert json.loads(json.dumps(plan)) == plan


def _spec(key: str, hints: dict) -> dict:
    return {"metadata": {key: hints}, "evidence": {"source_idea_ids": ["idea-1"]}}
