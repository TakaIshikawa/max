from __future__ import annotations

import json

from max.spec import generate_integration_backout_plan as exported_generator
from max.spec.integration_backout_plan import KIND, SCHEMA_VERSION, generate_integration_backout_plan


def test_integration_backout_plan_sorts_critical_integrations_first_and_uses_hints() -> None:
    plan = generate_integration_backout_plan(
        {
            "metadata": {
                "integration_backout": {
                    "integrations": [
                        {"name": "CRM", "owner": "revops", "criticality": "standard", "data_sync_direction": "inbound"},
                        {"name": "Billing", "owner": "finance", "criticality": "critical", "manual_fallback": "invoice upload"},
                    ],
                    "backout_triggers": ["billing errors"],
                }
            }
        }
    )

    assert plan["schema_version"] == SCHEMA_VERSION
    assert plan["kind"] == KIND
    assert [item["name"] for item in plan["integration_inventory"]] == ["Billing", "CRM"]
    assert plan["integration_inventory"][0]["manual_fallback"] == "invoice upload"
    assert plan["backout_triggers"][0]["trigger"] == "billing errors"
    assert exported_generator({})["kind"] == KIND


def test_integration_backout_plan_defaults_are_stable_and_json_serializable() -> None:
    first = generate_integration_backout_plan({})
    second = generate_integration_backout_plan({})

    assert first == second
    assert first["integration_inventory"][0]["name"] == "primary integration"
    assert first["reconciliation_checks"]
    assert json.loads(json.dumps(first))["kind"] == KIND
