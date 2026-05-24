from __future__ import annotations

from max.spec.vendor_data_deletion_attestation_plan import (
    generate_vendor_data_deletion_attestation_plan,
)


def test_vendor_data_deletion_attestation_plan_covers_multi_vendor_scope() -> None:
    plan = generate_vendor_data_deletion_attestation_plan(
        {
            "vendors": [
                {"vendor": "Acme Analytics", "contact": "privacy@acme.test", "due_date": "2026-06-10"},
                {"vendor": "Beta Storage", "contact": "dpo@beta.test", "data_category": "customer exports"},
            ],
            "data_categories": ["signals", "insights"],
            "evidence_items": ["signed deletion certificate"],
            "exceptions": [{"exception": "legal hold", "expiry": "2026-07-01"}],
        }
    )

    assert plan["title"] == "Vendor Data Deletion Attestation Plan"
    assert [vendor["name"] for vendor in plan["vendor_scope"]] == ["Acme Analytics", "Beta Storage"]
    assert plan["vendor_scope"][0]["contact"] == "privacy@acme.test"
    assert plan["exception_handling"][0]["exception"] == "legal hold"
    assert list(plan).index("attestation_request_steps") < list(plan).index("evidence_review")


def test_vendor_data_deletion_attestation_plan_defaults_missing_contact() -> None:
    plan = generate_vendor_data_deletion_attestation_plan({"vendors": [{"vendor": "No Contact Vendor"}]})

    assert plan["vendor_scope"][0]["name"] == "No Contact Vendor"
    assert "contact" not in plan["vendor_scope"][0]
    assert plan["attestation_request_steps"]
    assert plan["closure_criteria"][0]["name"] == (
        "all attestations received, exceptions approved, evidence archived, and requester notified"
    )


def test_vendor_data_deletion_attestation_plan_empty_input_fallback() -> None:
    plan = generate_vendor_data_deletion_attestation_plan({})

    assert plan["schema_version"] == "max.spec.vendor_data_deletion_attestation_plan.v1"
    assert plan["summary"]["vendor_count"] == 1
    assert plan["vendor_scope"][0]["contact"] == "vendor account owner"
