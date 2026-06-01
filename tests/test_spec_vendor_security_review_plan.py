from __future__ import annotations

import pytest

from max.spec.vendor_security_review_plan import SCHEMA_VERSION, generate_vendor_security_review_plan


def test_vendor_security_review_plan_high_risk_variant() -> None:
    plan = generate_vendor_security_review_plan(_spec("high"))

    assert plan["schema_version"] == SCHEMA_VERSION
    assert plan["review_scope"]["vendor"] == "Acme AI"
    assert [item["name"] for item in plan["evidence_collection"]] == ["DPA", "SOC 2"]
    assert plan["remediation_tasks"][0]["severity"] == "high"
    assert set(plan) >= {"questionnaire_review", "data_flow_assessment", "approval_criteria"}


def test_vendor_security_review_plan_low_risk_variant() -> None:
    plan = generate_vendor_security_review_plan(_spec("low"))

    assert plan["summary"]["risk_tier"] == "low"
    assert plan["remediation_tasks"][0]["severity"] == "medium"


@pytest.mark.parametrize("field", ["vendor_name", "risk_tier", "owner", "required_evidence"])
def test_vendor_security_review_plan_validates_required_fields(field: str) -> None:
    hints = dict(_spec("high")["metadata"]["vendor_security_review"])
    hints.pop(field)

    with pytest.raises(ValueError, match=field.replace("_", " ") if field != "required_evidence" else "evidence"):
        generate_vendor_security_review_plan({"metadata": {"vendor_security_review": hints}})


def test_vendor_security_review_plan_is_deterministic() -> None:
    assert generate_vendor_security_review_plan(_spec("high")) == generate_vendor_security_review_plan(_spec("high"))


def _spec(risk_tier: str) -> dict:
    return {
        "metadata": {
            "vendor_security_review": {
                "vendor_name": "Acme AI",
                "integration_scope": "support copilot",
                "data_exposure": "support tickets",
                "required_evidence": ["SOC 2", "DPA"],
                "owner": "security lead",
                "due_date": "2026-07-01",
                "risk_tier": risk_tier,
            }
        },
        "evidence": {"insight_ids": ["vsr-1"]},
    }
