from __future__ import annotations

from max.spec.vendor_continuity_review_plan import KIND, SCHEMA_VERSION, generate_vendor_continuity_review_plan


def test_vendor_continuity_review_plan_sorts_critical_vendors_first() -> None:
    plan = generate_vendor_continuity_review_plan(
        {
            "metadata": {
                "vendor_continuity_review": {
                    "vendors": [
                        {"name": "EmailCo", "critical": False, "contract": "MSA-1", "sla": "SLA-1"},
                        {"name": "PaymentsCo", "critical": True, "owner": "finance", "contract": "MSA-2", "sla": "SLA-2"},
                    ]
                }
            }
        }
    )

    assert plan["schema_version"] == SCHEMA_VERSION
    assert plan["kind"] == KIND
    assert [review["vendor"] for review in plan["vendor_reviews"]] == ["PaymentsCo", "EmailCo"]
    assert plan["vendor_reviews"][0]["priority"] == "critical"
    assert plan["signoffs"][0]["required"] is True


def test_vendor_continuity_review_plan_handles_replaceable_vendors() -> None:
    plan = generate_vendor_continuity_review_plan(
        {"vendors": [{"name": "SurveyCo", "critical": False, "owner": "ops", "contract": "contract-1", "sla": "sla-1"}]}
    )

    assert plan["continuity_risks"] == []
    assert plan["mitigation_actions"][0]["severity"] == "low"
    assert plan["replacement_options"][0]["strategy"] == "Document viable replacement at next renewal."
    assert plan["signoffs"][0]["required"] is False


def test_vendor_continuity_review_plan_creates_gaps_for_missing_contract_or_sla_evidence() -> None:
    plan = generate_vendor_continuity_review_plan(
        {
            "vendors": [{"name": "SearchCo", "critical": True, "contract": ""}],
            "evidence": {"signal_ids": ["vendor-1"]},
        }
    )

    assert plan["vendor_reviews"][0]["review_gaps"] == ["missing contract evidence", "missing SLA evidence"]
    assert plan["continuity_risks"][0]["severity"] == "critical"
    assert "missing contract evidence" in plan["continuity_risks"][0]["risk"]
    assert plan["continuity_risks"][0]["evidence_reference_ids"] == ["EV1"]
