from __future__ import annotations

import json

from max.spec.procurement_exception_review_plan import KIND, SCHEMA_VERSION, generate_procurement_exception_review_plan


def test_procurement_exception_review_holds_for_expired_exception() -> None:
    plan = generate_procurement_exception_review_plan(
        {
            "project": {"title": "Vendor Launch"},
            "evidence": {"insight_ids": ["proc-1"]},
            "metadata": {
                "procurement_exception_review": {
                    "exceptions": [{"name": "single source vendor", "severity": "high", "expiration": "expired", "owner": "Procurement"}],
                    "policy_gaps": ["competitive bid missing"],
                    "approver_signoffs": [{"name": "Finance", "status": "approved"}],
                }
            },
        }
    )

    assert plan["schema_version"] == SCHEMA_VERSION
    assert plan["kind"] == KIND
    assert plan["recommendation"] == "hold"
    assert plan["exception_reviews"][0]["severity"] == "high"
    assert plan["expiration_actions"][0]["action"] == "renew or close before use"
    assert plan["exception_reviews"][0]["evidence_reference_ids"] == ["EV1"]
    json.dumps(plan)


def test_procurement_exception_review_normalizes_string_inputs_and_fallbacks() -> None:
    plan = generate_procurement_exception_review_plan({"exceptions": ["low-risk renewal"]})

    assert plan["recommendation"] == "conditional"
    assert plan["exception_reviews"][0]["id"] == "PER1"
    assert plan["exception_reviews"][0]["name"] == "low-risk renewal"
    assert plan["policy_gaps"]
