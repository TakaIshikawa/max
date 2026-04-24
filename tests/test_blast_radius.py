"""Tests for idea blast-radius estimation."""

from __future__ import annotations

from max.analysis.blast_radius import estimate_idea_blast_radius
from max.types.buildable_unit import BuildableCategory, BuildableUnit
from max.types.evaluation import DimensionScore, UtilityEvaluation


def _dim(value: float) -> DimensionScore:
    return DimensionScore(value=value, confidence=0.7, reasoning="test")


def _evaluation(unit_id: str, build_effort: float) -> UtilityEvaluation:
    return UtilityEvaluation(
        buildable_unit_id=unit_id,
        pain_severity=_dim(7.0),
        addressable_scale=_dim(7.0),
        build_effort=_dim(build_effort),
        composability=_dim(7.0),
        competitive_density=_dim(7.0),
        timing_fit=_dim(7.0),
        compounding_value=_dim(7.0),
        overall_score=72.0,
        recommendation="yes",
    )


def test_blast_radius_is_deterministic_for_buildable_idea(sample_unit, sample_evaluation):
    first = estimate_idea_blast_radius(sample_unit, sample_evaluation)
    second = estimate_idea_blast_radius(sample_unit, sample_evaluation)

    assert first == second
    assert first.idea_id == "bu-test001"
    assert first.score > 0
    assert first.level in {"medium", "high", "critical"}
    assert first.affected_surfaces
    assert first.drivers
    assert first.mitigations
    assert 0.0 < first.confidence <= 0.95


def test_broad_integrated_high_effort_idea_scores_higher_than_narrow_idea():
    narrow = BuildableUnit(
        id="narrow",
        title="Markdown Formatter",
        one_liner="Format Markdown files locally",
        category=BuildableCategory.CLI_TOOL,
        problem="Markdown style differs across repos.",
        solution="Run a local formatter.",
        target_users="humans",
        value_proposition="Cleaner docs.",
        evidence_signals=["sig-1"],
        suggested_stack={"language": "python"},
        tech_approach="Small Python CLI.",
    )
    broad = BuildableUnit(
        id="broad",
        title="Enterprise Agent Workflow Platform",
        one_liner=(
            "Multi-tenant agent automation with Slack, GitHub, Jira, SSO, "
            "webhooks, and audit logs"
        ),
        category=BuildableCategory.APPLICATION,
        problem="Teams need agent workflow orchestration across internal systems.",
        solution=(
            "A cloud platform with OAuth, API sync, realtime dashboard, "
            "queue workers, and database migrations."
        ),
        target_users="both",
        value_proposition="Coordinate agent work across enterprise tools.",
        workflow_context="CI/CD and incident response automation",
        domain_risks=["security review", "privacy controls", "compliance audit"],
        evidence_signals=["sig-1", "sig-2", "sig-3"],
        inspiring_insights=["ins-1", "ins-2"],
        suggested_stack={"frontend": "react", "backend": "api", "database": "postgres"},
        tech_approach="Distributed backend, dashboard, OAuth integrations, scheduler, monitoring.",
    )

    narrow_estimate = estimate_idea_blast_radius(narrow, _evaluation("narrow", 8.5))
    broad_estimate = estimate_idea_blast_radius(broad, _evaluation("broad", 3.0))

    assert broad_estimate.score > narrow_estimate.score
    assert broad_estimate.level in {"high", "critical"}
    assert len(broad_estimate.affected_surfaces) > len(narrow_estimate.affected_surfaces)
    assert any(surface.name == "integrations" for surface in broad_estimate.affected_surfaces)
    assert any("high build effort" in driver for driver in broad_estimate.drivers)


def test_blast_radius_works_without_evaluation(sample_unit):
    estimate = estimate_idea_blast_radius(sample_unit)

    assert estimate.evaluation_available is False
    assert estimate.score > 0
    assert "utility evaluation is missing" in estimate.drivers
    assert any("Run utility evaluation" in item for item in estimate.mitigations)
