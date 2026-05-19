from __future__ import annotations

import json

from max.spec.integration_cutover_plan import (
    KIND,
    SCHEMA_VERSION,
    generate_integration_cutover_plan,
)


def test_integration_cutover_plan_reflects_customer_and_dependency_hints() -> None:
    plan = generate_integration_cutover_plan(
        {
            "source": {"idea_id": "cutover-1"},
            "project": {"title": "CRM Sync", "buyer": "RevOps"},
            "metadata": {
                "integration_cutover": {
                    "systems": ["Billing", "CRM"],
                    "cutover_window": "Sunday 01:00 UTC",
                    "freeze_period": "48 hours before cutover",
                    "external_dependencies": ["Salesforce"],
                    "customer_impacting": True,
                    "rollback_owner": "integration lead",
                    "validation_metrics": ["sync lag under 5 minutes"],
                }
            },
            "evidence": {"signal_ids": ["dep-1"]},
        }
    )

    assert plan["schema_version"] == SCHEMA_VERSION
    assert plan["kind"] == KIND
    assert plan["summary"]["customer_impacting"] is True
    assert plan["summary"]["external_dependency_count"] == 1
    assert [item["name"] for item in plan["dependency_readiness"]] == ["Billing", "CRM", "Salesforce"]
    assert any(item["id"] == "RT3" for item in plan["rollback_triggers"])
    assert plan["communications"][0]["timing"] == "T-24 hours"
    assert plan["owner_roles"][2]["suggested_owner"] == "integration lead"
    assert plan["evidence_references"] == [{"id": "EV1", "type": "signal", "reference": "signal:dep-1"}]
    json.dumps(plan)


def test_integration_cutover_plan_defaults_sparse_input() -> None:
    plan = generate_integration_cutover_plan({})

    assert plan["source"]["system"] == "max"
    assert plan["summary"]["system_count"] == 2
    assert [item["name"] for item in plan["dependency_readiness"]] == ["Primary application", "Integration endpoint"]
    assert len(plan["sequencing_steps"]) == 3
    assert plan["rollback_triggers"][0]["owner"] == "engineering_owner"
