from __future__ import annotations

import json
from unittest.mock import MagicMock

from max.spec.customer_acceptance_test_plan import (
    generate_customer_acceptance_test_plan,
    render_customer_acceptance_test_plan_markdown,
)


def _unit() -> MagicMock:
    unit = MagicMock()
    unit.id = "idea-cat"
    unit.title = "Enterprise Acceptance Workflow"
    unit.category = "feature"
    unit.domain = "enterprise"
    unit.status = "approved"
    unit.specific_user = "Customer QA Lead"
    unit.target_users = "operations teams"
    unit.buyer = "VP Operations"
    unit.workflow_context = "month-end acceptance"
    unit.solution = "Guided acceptance checklist"
    unit.validation_plan = "Run customer UAT with exported evidence"
    unit.evidence_rationale = "Pilot notes"
    unit.domain_risks = ["privacy review required"]
    return unit


def _evaluation() -> MagicMock:
    evaluation = MagicMock()
    evaluation.overall_score = 48
    evaluation.recommendation = "maybe"
    evaluation.weaknesses = ["Low confidence in customer rollout"]
    return evaluation


def test_customer_acceptance_plan_with_evaluation_is_deterministic() -> None:
    tact = {
        "source": {"idea_id": "idea-cat"},
        "project": {"title": "Enterprise Acceptance Workflow"},
        "execution": {"mvp_scope": ["Review generated packet"], "risks": ["compliance signoff"]},
        "acceptance_criteria": {"criteria": ["Customer can approve the packet", "Evidence exports are complete"]},
    }

    first = generate_customer_acceptance_test_plan(_unit(), _evaluation(), tact)
    second = generate_customer_acceptance_test_plan(_unit(), _evaluation(), tact)

    assert first == second
    assert json.loads(json.dumps(first))["kind"] == "max.spec.customer_acceptance_test_plan"
    assert first["schema_version"] == "max-customer-acceptance-test-plan/v1"
    assert first["source"]["idea_id"] == "idea-cat"
    assert first["summary"]["risk_level"] == "high"
    assert [row["id"] for row in first["acceptance_scenarios"]] == ["CAT-S1", "CAT-S2"]
    assert any(gate["approver"] == "VP Operations" for gate in first["sign_off_gates"])
    assert any(item["section"] == "sign_off_gates" for item in first["checklist_items"])


def test_customer_acceptance_plan_without_evaluation_uses_fallbacks() -> None:
    plan = generate_customer_acceptance_test_plan(_unit())

    assert plan["summary"]["risk_level"] == "high"
    assert plan["acceptance_scenarios"][0]["name"] == "Run customer UAT with exported evidence"
    assert plan["evidence_requirements"][0]["description"] == "Pilot notes"
    assert plan["sign_off_gates"][0]["evaluation_context"] == "not evaluated"


def test_customer_acceptance_markdown_renders_scenarios_and_gates() -> None:
    markdown = render_customer_acceptance_test_plan_markdown(generate_customer_acceptance_test_plan(_unit(), _evaluation()))

    assert "## Acceptance Scenarios" in markdown
    assert "CAT-S1" in markdown
    assert "## Sign-Off Gates" in markdown
    assert "VP Operations sign-off" in markdown
