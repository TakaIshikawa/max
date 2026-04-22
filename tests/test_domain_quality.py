from __future__ import annotations

from max.profiles.schema import DomainContext, DomainQualityConfig, DomainQualityDimension
from max.quality.gate import enforce_domain_quality_gate
from max.quality.scorer import score_domain_quality
from max.types.buildable_unit import BuildableUnit


def _config() -> DomainQualityConfig:
    return DomainQualityConfig(
        enabled=True,
        min_score=65.0,
        required_fields=["buyer", "workflow_context", "validation_plan"],
        scoring_dimensions={
            "workflow_specificity": DomainQualityDimension(weight=1.4),
            "buyer_clarity": DomainQualityDimension(weight=1.2),
            "evidence_support": DomainQualityDimension(weight=1.3),
            "implementation_feasibility": DomainQualityDimension(weight=1.0),
            "differentiation": DomainQualityDimension(weight=1.0),
            "distribution_path": DomainQualityDimension(weight=1.0),
        },
        hard_rejections=["missing_buyer", "missing_workflow", "generic_ai_assistant"],
        rejected_patterns=["generic coding assistant"],
    )


def _domain() -> DomainContext:
    return DomainContext(
        name="developer-tools",
        description="Developer tools",
        categories=["cli_tool"],
        target_user_types=["developers"],
        bad_idea_patterns=["generic coding assistant"],
    )


def test_domain_quality_passes_specific_workflow_idea() -> None:
    unit = BuildableUnit(
        id="bu-good",
        title="Agent CI Harness",
        one_liner="CLI evaluation harness for agent release gates",
        category="cli_tool",
        problem="Teams cannot verify agent behavior before release.",
        solution="Run workflow fixtures in CI and block risky releases.",
        value_proposition="Safer agent releases.",
        buyer="engineering manager",
        specific_user="platform engineer",
        workflow_context="CI gate before production deployment",
        validation_plan="Run against three open-source agent repos.",
        evidence_rationale="Multiple teams report failed agent releases.",
        tech_approach="Python CLI with YAML fixtures",
        inspiring_insights=["ins-1"],
    )

    scores = score_domain_quality([unit], domain=_domain(), config=_config(), profile_name="devtools")
    kept, rejected = enforce_domain_quality_gate([unit], scores)

    assert len(kept) == 1
    assert rejected == []
    assert scores[0].passed_gate is True
    assert scores[0].overall_score >= 65


def test_domain_quality_rejects_generic_missing_buyer_idea() -> None:
    unit = BuildableUnit(
        id="bu-bad",
        title="Generic Coding Assistant",
        one_liner="Generic AI assistant for all developers",
        category="application",
        problem="Developers need help.",
        solution="A chatbot dashboard for coding.",
        value_proposition="More productivity.",
    )

    scores = score_domain_quality([unit], domain=_domain(), config=_config(), profile_name="devtools")
    kept, rejected = enforce_domain_quality_gate([unit], scores)

    assert kept == []
    assert len(rejected) == 1
    assert scores[0].passed_gate is False
    assert "missing_buyer" in scores[0].rejection_tags
    assert "missing_workflow" in scores[0].rejection_tags


def test_ai_infrastructure_rubric_rewards_measurable_deployment_fit() -> None:
    config = DomainQualityConfig(
        enabled=True,
        min_score=65.0,
        required_fields=["buyer", "specific_user", "workflow_context", "validation_plan", "tech_approach"],
        scoring_dimensions={
            "measurable_infra_impact": DomainQualityDimension(weight=1.5),
            "deployment_fit": DomainQualityDimension(weight=1.2),
            "workflow_specificity": DomainQualityDimension(weight=1.0),
            "buyer_clarity": DomainQualityDimension(weight=1.0),
        },
        hard_rejections=["missing_buyer", "missing_workflow"],
    )
    domain = DomainContext(
        name="ai-infrastructure",
        description="AI infrastructure",
        categories=["serving_platform"],
        target_user_types=["platform_engineers"],
        bad_idea_patterns=["generic LLM observability dashboard"],
    )
    unit = BuildableUnit(
        id="bu-ai-infra",
        title="vLLM Latency Profiler",
        one_liner="CLI that profiles vLLM deployments and recommends GPU batch settings.",
        category="serving_platform",
        problem="Platform teams cannot predict latency and GPU utilization before model rollout.",
        solution="Run benchmark traffic against a Kubernetes vLLM deployment and compare tokens/sec, latency, and GPU utilization.",
        value_proposition="Reduce inference cost and rollout risk.",
        buyer="head of ML platform",
        specific_user="ML platform engineer",
        workflow_context="pre-production inference deployment validation",
        validation_plan="Run against two open models on a local vLLM stack.",
        tech_approach="Python CLI that calls vLLM metrics APIs and emits CI artifacts.",
    )

    score = score_domain_quality([unit], domain=domain, config=config, profile_name="ai-infra")[0]

    assert score.passed_gate is True
    assert score.dimensions["measurable_infra_impact"] >= 8.0
    assert score.dimensions["deployment_fit"] >= 8.0
