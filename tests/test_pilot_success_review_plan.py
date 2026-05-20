from __future__ import annotations

from unittest.mock import MagicMock

from max.spec.pilot_success_review_plan import generate_pilot_success_review_plan, render_pilot_success_review_plan_markdown


def _unit() -> MagicMock:
    unit = MagicMock()
    unit.id = "pilot-1"
    unit.title = "Claims Pilot"
    unit.domain = "insurance"
    unit.buyer = "Claims VP"
    unit.specific_user = "Pilot Lead"
    unit.value_proposition = "Reduce claims handling time"
    unit.validation_plan = "Run two-week customer pilot"
    unit.evidence_rationale = "Customer interview evidence"
    return unit


def _evaluation(score: float = 52, recommendation: str = "maybe") -> MagicMock:
    evaluation = MagicMock()
    evaluation.overall_score = score
    evaluation.recommendation = recommendation
    evaluation.weaknesses = ["Adoption risk"]
    evaluation.strengths = ["High pain"]
    return evaluation


def test_pilot_success_review_evaluation_influences_decision_criteria() -> None:
    plan = generate_pilot_success_review_plan(_unit(), _evaluation(), {"execution": {"success_metrics": ["Cycle time improves"]}})

    assert plan["kind"] == "max.spec.pilot_success_review_plan"
    assert plan["summary"]["evaluation_score"] == 52.0
    assert plan["success_metrics"][0]["target"] == "requires mitigation plan before expansion"
    assert "weaknesses" in plan["decision_criteria"][0]["condition"]


def test_pilot_success_review_uses_deterministic_fallbacks_without_evaluation() -> None:
    first = generate_pilot_success_review_plan(_unit())
    second = generate_pilot_success_review_plan(_unit())

    assert first == second
    assert first["summary"]["recommendation"] == "not_evaluated"
    assert first["decision_criteria"][0]["condition"] == "customer sponsor confirms value and no unresolved blocker"
    assert first["review_agenda"][0]["topic"] == "Pilot goals recap"


def test_pilot_success_review_markdown_renders_review_package() -> None:
    markdown = render_pilot_success_review_plan_markdown(generate_pilot_success_review_plan(_unit(), _evaluation(82, "yes")))

    assert "## Pilot Goals" in markdown
    assert "## Evidence Requests" in markdown
    assert "## Decision Criteria" in markdown
