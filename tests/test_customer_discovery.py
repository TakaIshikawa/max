"""Tests for deterministic customer discovery script generation."""

from __future__ import annotations

from max.analysis.customer_discovery import generate_customer_discovery_script
from max.types.buildable_unit import BuildableCategory, BuildableUnit
from max.types.evaluation import DimensionScore, UtilityEvaluation


def _evaluation(unit_id: str) -> UtilityEvaluation:
    score = DimensionScore(value=8.0, confidence=0.7, reasoning="seeded")
    return UtilityEvaluation(
        buildable_unit_id=unit_id,
        pain_severity=score,
        addressable_scale=score,
        build_effort=score,
        composability=score,
        competitive_density=score,
        timing_fit=score,
        compounding_value=score,
        overall_score=82.5,
        strengths=["Urgent workflow pain"],
        weaknesses=["Buyer path unclear"],
        recommendation="yes",
    )


def test_customer_discovery_script_uses_rich_buyer_user_workflow_fields() -> None:
    unit = BuildableUnit(
        id="bu-discovery-rich",
        title="Claims Review Copilot",
        one_liner="Speed up insurance claims review",
        category=BuildableCategory.APPLICATION,
        problem="claims adjusters miss policy exceptions during manual review",
        solution="an AI-assisted review queue that highlights exception risk",
        value_proposition="reduce rework and leakage in complex claims",
        specific_user="senior claims adjuster",
        buyer="claims operations VP",
        workflow_context="high-value property claim review",
        current_workaround="spreadsheet checklists and peer review",
        why_now="claim severity and staffing pressure are rising",
        validation_plan="interview 10 adjusters and run a concierge review test",
        first_10_customers="regional insurers with complex property books",
    )

    script = generate_customer_discovery_script(
        unit,
        evaluation=_evaluation(unit.id),
        evidence_density={"density_score": 64.2, "signal_count": 3},
    )

    assert script["idea_id"] == unit.id
    assert any("senior claims adjuster" in profile for profile in script["target_respondent_profiles"])
    assert any("claims operations VP" in profile for profile in script["target_respondent_profiles"])
    assert any("high-value property claim review" in question["prompt"] for question in script["screening_questions"])
    assert any("82.5/100" in goal for goal in script["interview_goals"])
    assert any("density score of 64.2" in signal for signal in script["success_signals"])
    assert set(script["sections"]) == {"screening", "interview", "follow_up"}


def test_customer_discovery_script_handles_sparse_ideas() -> None:
    unit = BuildableUnit(
        id="bu-discovery-sparse",
        title="Ops Helper",
        one_liner="Help ops teams",
        category=BuildableCategory.AUTOMATION,
        problem="ops work is scattered",
        solution="centralize recurring ops tasks",
        value_proposition="save coordination time",
    )

    script = generate_customer_discovery_script(unit)

    assert script["target_respondent_profiles"]
    assert len(script["screening_questions"]) >= 3
    assert len(script["discovery_questions"]) >= 5
    assert len(script["demo_prompts"]) >= 3
    assert len(script["follow_up_artifacts"]) >= 3
    assert any("prospective user" in profile or "both" in profile for profile in script["target_respondent_profiles"])


def test_customer_discovery_script_incorporates_validation_experiments() -> None:
    unit = BuildableUnit(
        id="bu-discovery-vexp",
        title="FinOps Alert Router",
        one_liner="Route noisy cloud cost alerts",
        category=BuildableCategory.AUTOMATION,
        problem="teams ignore cost alerts because ownership is unclear",
        solution="route alerts to service owners with context",
        value_proposition="cut wasted cloud spend faster",
        workflow_context="weekly cloud cost review",
    )
    experiments = [
        {
            "id": "vexp-1",
            "hypothesis": "service owners will accept routed alerts when context includes spend delta",
            "method": "concierge test",
            "success_metric": "5 of 8 owners take action within 48 hours",
            "status": "planned",
        }
    ]

    script = generate_customer_discovery_script(unit, validation_experiments=experiments)

    assert any("validation experiments" in goal for goal in script["interview_goals"])
    assert any(
        "service owners will accept routed alerts" in question["prompt"]
        for question in script["disconfirming_questions"]
    )
    assert any(
        "5 of 8 owners take action" in signal
        for signal in script["success_signals"]
    )
    assert any("Validation experiment updates" in artifact for artifact in script["follow_up_artifacts"])
