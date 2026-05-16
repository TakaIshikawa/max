from __future__ import annotations

import json

from max.spec.data_deletion_verification_plan import (
    DATA_DELETION_VERIFICATION_PLAN_SCHEMA_VERSION,
    KIND,
    generate_data_deletion_verification_plan,
)


def _spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {"idea_id": "delete-1", "domain": "privacy"},
        "project": {
            "title": "Customer Privacy Portal",
            "workflow_context": "customer account deletion",
            "specific_user": "privacy operator",
            "buyer": "privacy lead",
        },
        "execution": {"mvp_scope": ["self-service deletion", "admin override"]},
        "privacy": {
            "deletion_scope": [
                "Customer account records",
                "Analytics events and logs",
                "Processor integration copies",
            ]
        },
        "evidence": {
            "insight_ids": ["ins-1"],
            "signal_ids": ["sig-1"],
            "rationale": "Enterprise buyers need deletion proof.",
        },
    }


def test_data_deletion_verification_plan_complete_shape() -> None:
    plan = generate_data_deletion_verification_plan(_spec())

    assert plan["schema_version"] == DATA_DELETION_VERIFICATION_PLAN_SCHEMA_VERSION
    assert plan["kind"] == KIND
    assert plan["source"]["idea_id"] == "delete-1"
    assert plan["summary"]["title"] == "Customer Privacy Portal"
    assert plan["summary"]["deletion_scope_count"] == 3
    assert [item["category"] for item in plan["deletion_scope"]] == [
        "customer_data",
        "logs_and_telemetry",
        "processor_copy",
    ]
    assert [item["id"] for item in plan["verification_checks"]] == ["VC1", "VC2", "VC3", "VC4"]
    assert plan["verification_checks"][0]["scope_references"] == ["DS1", "DS2", "DS3"]
    assert [item["id"] for item in plan["evidence_requirements"]] == ["ER1", "ER2", "ER3", "ER4"]
    assert {item["role"] for item in plan["owner_roles"]} == {
        "privacy_owner",
        "data_owner",
        "engineering_owner",
        "support_owner",
    }
    assert [item["id"] for item in plan["exception_handling"]] == ["EX1", "EX2", "EX3"]
    assert [item["reference"] for item in plan["evidence_references"]] == [
        "insight:ins-1",
        "signal:sig-1",
        "Enterprise buyers need deletion proof.",
    ]
    assert json.loads(json.dumps(plan))["kind"] == KIND


def test_data_deletion_verification_plan_sparse_input_defaults() -> None:
    plan = generate_data_deletion_verification_plan({})

    assert plan["summary"]["title"] == "Untitled TactSpec"
    assert plan["summary"]["workflow_context"] == "primary workflow"
    assert plan["summary"]["target_user"] == "primary user"
    assert plan["summary"]["buyer"] == "launch sponsor"
    assert plan["deletion_scope"][0]["name"] == "Customer records for primary workflow"
    assert plan["deletion_scope"][0]["owner"] == "data_owner"
    assert plan["evidence_references"] == []
    assert plan["verification_checks"][2]["owner"] == "privacy_owner"


def test_data_deletion_verification_plan_is_deterministic() -> None:
    first = generate_data_deletion_verification_plan(_spec())
    second = generate_data_deletion_verification_plan(_spec())

    assert first == second
