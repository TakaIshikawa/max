from __future__ import annotations

import json

from max.spec import generate_data_contract_change_plan as exported_generator
from max.spec.data_contract_change_plan import KIND, SCHEMA_VERSION, generate_data_contract_change_plan


def test_data_contract_change_plan_uses_metadata_hints() -> None:
    plan = generate_data_contract_change_plan(
        {
            "source": {"idea_id": "contract-1"},
            "project": {"title": "Ledger Events", "specific_user": "finance analyst"},
            "metadata": {
                "data_contract_change": {
                    "contract": "ledger-event-v2",
                    "breaking_change": True,
                    "producers": [{"name": "Billing API", "owner": "billing", "impact": "adds required invoice_id"}],
                    "consumers": [{"name": "Warehouse", "owner": "data"}],
                    "rollout_gates": ["consumer replay passes"],
                    "rollback_criteria": ["warehouse validation fails"],
                }
            },
        }
    )

    assert plan["schema_version"] == SCHEMA_VERSION
    assert plan["kind"] == KIND
    assert plan["summary"]["breaking_change_severity"] == "breaking"
    assert [item["name"] for item in plan["impacted_parties"]] == ["Warehouse", "Billing API"]
    assert plan["rollout_gates"][0]["name"] == "consumer replay passes"
    assert plan["rollback_criteria"][0]["name"] == "warehouse validation fails"
    assert exported_generator({"metadata": {}})["kind"] == KIND


def test_data_contract_change_plan_sparse_defaults_are_deterministic_and_json_serializable() -> None:
    first = generate_data_contract_change_plan({})
    second = generate_data_contract_change_plan({})

    assert first == second
    assert first["summary"]["producer_count"] == 1
    assert first["summary"]["consumer_count"] == 1
    assert first["compatibility_checks"]
    assert json.loads(json.dumps(first))["kind"] == KIND
