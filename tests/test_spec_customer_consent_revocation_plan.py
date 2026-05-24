from __future__ import annotations

from max.spec.customer_consent_revocation_plan import generate_customer_consent_revocation_plan


def test_customer_consent_revocation_plan_preserves_traceable_scope_and_destinations() -> None:
    plan = generate_customer_consent_revocation_plan(
        {
            "metadata": {
                "customer_consent_revocation": {
                    "consent_scope": [
                        {
                            "customer_id": "cust-123",
                            "consent_artifact": "consent-ledger:event-9",
                            "purpose": "marketing insights",
                        }
                    ],
                    "affected_data_classes": ["feedback records", "derived insights"],
                    "downstream_destinations": [{"destination": "Salesforce", "status": "queued"}],
                    "verification": ["lineage query shows no active publications"],
                }
            },
            "evidence": {"insight_ids": ["consent-1"]},
        }
    )

    assert plan["title"] == "Customer Consent Revocation Plan"
    assert set(plan) >= {
        "consent_scope",
        "affected_data_classes",
        "revocation_workflow",
        "downstream_propagation",
        "verification_evidence",
        "customer_communication",
        "owner_checklist",
    }
    assert plan["consent_scope"][0]["customer_id"] == "cust-123"
    assert plan["consent_scope"][0]["consent_artifact"] == "consent-ledger:event-9"
    assert plan["downstream_propagation"][0]["destination"] == "Salesforce"
    assert plan["verification_evidence"][0]["evidence_reference_ids"] == ["EV1"]


def test_customer_consent_revocation_plan_defaults_empty_input() -> None:
    plan = generate_customer_consent_revocation_plan({})

    assert plan["schema_version"] == "max.spec.customer_consent_revocation_plan.v1"
    assert plan["summary"]["consent_record_count"] == 1
    assert plan["consent_scope"][0]["customer_id"] == "unknown customer"
    assert plan["affected_data_classes"][0]["name"] == (
        "signals, feedback records, derived insights, exports, and publication destinations"
    )


def test_customer_consent_revocation_plan_accepts_raw_downstream_destinations() -> None:
    plan = generate_customer_consent_revocation_plan(
        {"downstream_destinations": [{"destination": "Zendesk"}, {"destination": "Customer Portal"}]}
    )

    assert [item["destination"] for item in plan["downstream_propagation"]] == [
        "Customer Portal",
        "Zendesk",
    ]
