from __future__ import annotations

import json

from max.spec.data_residency_verification_plan import generate_data_residency_verification_plan


def test_data_residency_verification_plan_adds_restricted_region_customer_steps() -> None:
    plan = generate_data_residency_verification_plan(
        {
            "metadata": {
                "data_residency": {
                    "regions": ["eu-central-1"],
                    "restricted_regions": ["us-east-1"],
                    "data_classes": ["PII"],
                    "systems": ["warehouse"],
                    "customer_attestation_required": True,
                }
            }
        }
    )

    assert plan["kind"] == "max.spec.data_residency_verification_plan"
    assert plan["summary"]["restricted_regions"] == ["us-east-1"]
    assert plan["summary"]["customer_attestation_required"] is True
    assert plan["verification_checks"][-1]["name"] == "restricted_region_scan"
    assert plan["exception_handling"][0]["severity"] == "critical"
    assert "Publish customer-facing" in plan["customer_attestations"][0]["description"]
    json.dumps(plan)


def test_data_residency_verification_plan_defaults_sparse_input() -> None:
    plan = generate_data_residency_verification_plan({})

    assert plan["summary"]["approved_regions"] == ["us-east-1"]
    assert [item["name"] for item in plan["data_locations"]] == ["application datastore", "object storage"]
    assert plan["summary"]["verification_cadence"] == "quarterly"
    assert len(plan["owner_roles"]) == 3
