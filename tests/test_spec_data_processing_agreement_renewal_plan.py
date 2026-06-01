from __future__ import annotations

import pytest

from max.spec.data_processing_agreement_renewal_plan import generate_data_processing_agreement_renewal_plan


def test_data_processing_agreement_renewal_plan_sorts_waves_by_urgency() -> None:
    plan = generate_data_processing_agreement_renewal_plan(_spec())

    assert [item["name"] for item in plan["renewal_waves"]] == ["Overdue Customer", "Ownerless Vendor", "Soon Customer"]
    assert [item["name"] for item in plan["jurisdiction_groups"]] == ["EU", "US"]
    assert set(plan) >= {"verification_steps", "customer_communication_checks", "approval_gates"}


def test_data_processing_agreement_renewal_plan_surfaces_blockers() -> None:
    plan = generate_data_processing_agreement_renewal_plan(_spec())

    assert [item["description"] for item in plan["escalations"]] == [
        "Resolve blocker for Overdue Customer: overdue agreement.",
        "Resolve blocker for Ownerless Vendor: missing owner.",
    ]


def test_data_processing_agreement_renewal_plan_is_deterministic() -> None:
    assert generate_data_processing_agreement_renewal_plan(_spec()) == generate_data_processing_agreement_renewal_plan(_spec())


def test_data_processing_agreement_renewal_plan_requires_agreements() -> None:
    with pytest.raises(ValueError, match="agreements"):
        generate_data_processing_agreement_renewal_plan({"metadata": {"data_processing_agreement_renewal": {}}})


def _spec() -> dict:
    return {
        "metadata": {
            "data_processing_agreement_renewal": {
                "agreements": [
                    {"name": "Soon Customer", "owner": "legal", "expiry_date": "2026-07-01", "jurisdiction": "EU", "subprocessors": ["Cloud A"], "customer_impact": "notice required"},
                    {"name": "Ownerless Vendor", "expiry_date": "2026-06-15", "jurisdiction": "US"},
                    {"name": "Overdue Customer", "owner": "privacy", "expiry_date": "overdue 2026-05-01", "jurisdiction": "EU", "status": "overdue"},
                ]
            }
        }
    }
