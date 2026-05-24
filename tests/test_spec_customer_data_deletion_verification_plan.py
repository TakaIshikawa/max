from __future__ import annotations

from max.spec.customer_data_deletion_verification_plan import (
    KIND,
    generate_customer_data_deletion_verification_plan,
)


def test_customer_data_deletion_verification_plan_separates_verification_areas() -> None:
    plan = generate_customer_data_deletion_verification_plan(
        {
            "id": "spec-1",
            "metadata": {
                "customer_data_deletion_verification": {
                    "customers": [{"customer": "Acme", "request_id": "dsr-1"}],
                    "systems": ["primary db"],
                    "downstream_destinations": ["crm"],
                }
            },
        }
    )

    assert plan["kind"] == KIND
    assert plan["summary"]["deletion_scope_count"] == 1
    assert plan["deletion_scope"][0]["name"] == "Acme"
    assert plan["affected_systems"][0]["name"] == "primary db"
    assert plan["backup_verification"]
    assert plan["downstream_destinations"][0]["name"] == "crm"
    assert plan["customer_communication"]
    assert plan["residual_retention_signoff"]


def test_customer_data_deletion_verification_plan_defaults() -> None:
    plan = generate_customer_data_deletion_verification_plan({})

    assert plan["deletion_scope"][0]["name"] == "customer deletion request"
    assert plan["backup_verification"][0]["owner"] == "privacy_owner"
