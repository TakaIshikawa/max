from __future__ import annotations

import pytest

from max.spec.data_processor_subcontractor_risk_reassessment_plan import generate_data_processor_subcontractor_risk_reassessment_plan


def test_data_processor_subcontractor_reassessment_sorts_subcontractors_and_escalates() -> None:
    plan = generate_data_processor_subcontractor_risk_reassessment_plan(
        {
            "metadata": {
                "data_processor_subcontractor_risk_reassessment": {
                    "processor": "Acme Processor",
                    "subcontractors": [{"name": "Zulu Ops"}, {"name": "Alpha Hosting"}, {"name": "Zulu Ops"}],
                    "jurisdictions": ["Germany", "China"],
                    "data_categories": ["email", "usage"],
                    "owner": "privacy_owner",
                    "legal_reviewer": "legal_owner",
                }
            }
        }
    )

    assert [item["name"] for item in plan["inventory"]] == ["Alpha Hosting", "Zulu Ops"]
    assert plan["jurisdiction_review"][-1]["name"] == "High-risk jurisdiction escalation"
    assert plan["jurisdiction_review"][-1]["severity"] == "high"


def test_data_processor_subcontractor_reassessment_validates_required_fields() -> None:
    with pytest.raises(ValueError, match="legal_reviewer"):
        generate_data_processor_subcontractor_risk_reassessment_plan({"metadata": {"data_processor_subcontractor_risk_reassessment": {"processor": "Acme"}}})
