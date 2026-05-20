from __future__ import annotations

from unittest.mock import MagicMock

from max.spec.data_access_request_fulfillment_plan import generate_data_access_request_fulfillment_plan, render_data_access_request_fulfillment_plan_markdown


def _unit() -> MagicMock:
    unit = MagicMock()
    unit.id = "dar-1"
    unit.title = "Customer Data Request"
    unit.domain = "privacy"
    unit.category = "automation"
    unit.domain_risks = ["privacy compliance"]
    return unit


def _evaluation() -> MagicMock:
    evaluation = MagicMock()
    evaluation.overall_score = 55
    evaluation.weaknesses = ["legal review needed"]
    return evaluation


def test_data_access_plan_uses_unit_domain_for_data_scope() -> None:
    plan = generate_data_access_request_fulfillment_plan(_unit())

    assert plan["kind"] == "max.spec.data_access_request_fulfillment_plan"
    assert [row["scope"] for row in plan["data_scope"]][:2] == ["privacy", "automation"]
    assert plan["intake_fields"][0]["field"] == "requester identity"


def test_data_access_plan_adds_stricter_audit_evidence_for_risk() -> None:
    plan = generate_data_access_request_fulfillment_plan(_unit(), _evaluation())

    assert any(item["evidence"] == "legal review note" for item in plan["audit_evidence"])
    assert any(step["step"] == "perform secondary privacy review" for step in plan["verification_steps"])


def test_data_access_markdown_renders_evidence() -> None:
    markdown = render_data_access_request_fulfillment_plan_markdown(generate_data_access_request_fulfillment_plan(_unit(), _evaluation()))

    assert "## Data Scope" in markdown
    assert "## Audit Evidence" in markdown
    assert "legal review note" in markdown
