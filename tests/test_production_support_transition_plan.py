from __future__ import annotations

from unittest.mock import MagicMock

from max.spec.production_support_transition_plan import generate_production_support_transition_plan, render_production_support_transition_plan_markdown


def _unit() -> MagicMock:
    unit = MagicMock()
    unit.id = "prod-1"
    unit.title = "Production Claims Workflow"
    unit.domain = "enterprise"
    unit.buyer = "Ops VP"
    unit.workflow_context = "claims intake"
    unit.solution = "automated workflow"
    unit.domain_risks = ["customer outage risk"]
    return unit


def _evaluation(score: float) -> MagicMock:
    evaluation = MagicMock()
    evaluation.overall_score = score
    evaluation.weaknesses = ["support coverage gap"]
    return evaluation


def test_support_transition_low_score_produces_stricter_gates() -> None:
    plan = generate_production_support_transition_plan(_unit(), _evaluation(50))

    assert plan["kind"] == "max.spec.production_support_transition_plan"
    assert any(gate["gate"] == "executive launch support approval" for gate in plan["readiness_gates"])
    assert plan["triage_rules"][0]["response_time"] == "15 minutes"


def test_support_transition_markdown_renders_owner_matrix_and_triage_rules() -> None:
    markdown = render_production_support_transition_plan_markdown(generate_production_support_transition_plan(_unit(), _evaluation(85)))

    assert "## Owner Matrix" in markdown
    assert "support_owner" in markdown
    assert "## Triage Rules" in markdown
    assert "sev1" in markdown
