from __future__ import annotations

from unittest.mock import MagicMock

from max.spec.customer_validation_evidence_plan import generate_customer_validation_evidence_plan, render_customer_validation_evidence_plan_markdown


def _unit() -> MagicMock:
    unit = MagicMock()
    unit.id = "val-1"
    unit.title = "Validation Evidence"
    unit.domain = "growth"
    unit.buyer = "Growth VP"
    unit.value_proposition = "Reduce onboarding time"
    unit.problem = "Customers abandon onboarding"
    unit.first_10_customers = "enterprise admins"
    unit.specific_user = "Admin lead"
    unit.target_users = "admins"
    return unit


def _evaluation(score: float) -> MagicMock:
    evaluation = MagicMock()
    evaluation.overall_score = score
    return evaluation


def test_customer_validation_uses_unit_fields_for_hypotheses_and_segments() -> None:
    plan = generate_customer_validation_evidence_plan(_unit())

    assert plan["kind"] == "max.spec.customer_validation_evidence_plan"
    assert plan["validation_hypotheses"][0]["hypothesis"] == "Reduce onboarding time"
    assert plan["customer_segments"][0]["segment"] == "enterprise admins"
    assert plan["evidence_requests"][0]["segment"] == "enterprise admins"


def test_customer_validation_evaluation_influences_confidence_thresholds() -> None:
    plan = generate_customer_validation_evidence_plan(_unit(), _evaluation(50))

    assert plan["confidence_scoring"][0]["minimum_confidence"] == 4
    assert plan["decision_thresholds"][0]["threshold"] == "average confidence >= 4 with no critical objections"


def test_customer_validation_markdown_includes_evidence_requests() -> None:
    markdown = render_customer_validation_evidence_plan_markdown(generate_customer_validation_evidence_plan(_unit(), _evaluation(80)))

    assert "## Evidence Requests" in markdown
    assert "Collect interview evidence" in markdown
