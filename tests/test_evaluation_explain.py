"""Tests for deterministic evaluation explanations."""

from __future__ import annotations

from max.evaluation.explain import explain_evaluation
from max.types.buildable_unit import BuildableUnit
from max.types.evaluation import DimensionScore, UtilityEvaluation
from max.types.insight import Insight
from max.types.signal import Signal, SignalSourceType


def _score(value: float, confidence: float = 0.8, reasoning: str = "reason") -> DimensionScore:
    return DimensionScore(value=value, confidence=confidence, reasoning=reasoning)


def _evaluation() -> UtilityEvaluation:
    return UtilityEvaluation(
        buildable_unit_id="bu-explain",
        pain_severity=_score(9.0, reasoning="Pain is frequent."),
        addressable_scale=_score(6.0, reasoning="Market is plausible."),
        build_effort=_score(8.0, reasoning="MVP is straightforward."),
        composability=_score(8.5, reasoning="Integrates cleanly."),
        competitive_density=_score(5.0, reasoning="Several alternatives exist."),
        timing_fit=_score(7.0, reasoning="Timing is good."),
        compounding_value=_score(4.5, reasoning="Value is mostly linear."),
        overall_score=72.0,
        strengths=["Strong workflow fit"],
        weaknesses=["Needs better market proof"],
        recommendation="yes",
        weights_used={
            "pain_severity": 0.20,
            "addressable_scale": 0.15,
            "build_effort": 0.15,
            "composability": 0.15,
            "competitive_density": 0.10,
            "timing_fit": 0.10,
            "compounding_value": 0.15,
        },
    )


def test_explain_evaluation_uses_scores_evidence_and_missing_fields() -> None:
    unit = BuildableUnit(
        id="bu-explain",
        title="Evidence explainer",
        one_liner="Explains a score",
        category="application",
        problem="Teams cannot see why an idea scored well.",
        solution="Show deterministic scoring drivers and evidence gaps.",
        target_users="humans",
        value_proposition="Faster review decisions",
        specific_user="pipeline reviewer",
        workflow_context="weekly idea review",
        validation_plan="Review explanations with five pipeline users.",
        inspiring_insights=["ins-explain"],
        evidence_signals=["sig-forum", "sig-registry"],
        evidence_rationale="Reviewers need transparent evidence-backed decisions.",
    )
    insight = Insight(
        id="ins-explain",
        category="gap",
        title="Reviewers ask why",
        summary="Reviewers need transparent scoring.",
        evidence=["sig-roadmap"],
    )
    signals = [
        Signal(
            id="sig-forum",
            source_type=SignalSourceType.FORUM,
            source_adapter="reddit",
            title="Forum pain",
            content="Why did this score high?",
            url="https://example.com/forum",
            credibility=0.7,
            metadata={"signal_role": "problem"},
        ),
        Signal(
            id="sig-registry",
            source_type=SignalSourceType.REGISTRY,
            source_adapter="github",
            title="Existing usage",
            content="Review tooling demand.",
            url="https://example.com/registry",
            credibility=0.8,
            metadata={"signal_role": "market"},
        ),
        Signal(
            id="sig-roadmap",
            source_type=SignalSourceType.ROADMAP,
            source_adapter="vendor",
            title="Vendor roadmap",
            content="Review APIs are opening.",
            url="https://example.com/roadmap",
            credibility=0.9,
            metadata={"signal_role": "solution"},
        ),
    ]

    explanation = explain_evaluation(
        unit,
        _evaluation(),
        insights=[insight],
        signals=signals,
    )

    assert explanation["idea_id"] == "bu-explain"
    assert explanation["recommendation"] == "yes"
    assert explanation["top_positive_drivers"][0]["dimension"] == "pain_severity"
    assert any(
        driver["dimension"] == "compounding_value" for driver in explanation["top_negative_drivers"]
    )
    assert len(explanation["dimension_notes"]) == 7
    assert explanation["evidence_diversity"]["source_count"] == 3
    assert explanation["evidence_diversity"]["diversity_score"] > 80
    assert any(
        "triangulated across 3 adapters" in hint for hint in explanation["triangulation_hints"]
    )
    assert any(item["field"] == "buyer" for item in explanation["missing_field_penalties"])
    assert explanation["recommended_next_evidence"]


def test_explain_evaluation_recommends_more_evidence_when_evidence_is_thin() -> None:
    unit = BuildableUnit(
        id="bu-thin",
        title="Thin evidence idea",
        one_liner="Needs support",
        category="application",
        problem="Problem statement",
        solution="Solution statement",
        value_proposition="Value statement",
    )
    evaluation = _evaluation()
    evaluation.buildable_unit_id = "bu-thin"

    explanation = explain_evaluation(unit, evaluation)

    assert explanation["evidence_diversity"]["signal_count"] == 0
    assert explanation["evidence_diversity"]["source_count"] == 0
    assert any(item["field"] == "evidence" for item in explanation["missing_field_penalties"])
    assert any(
        "independent source adapter" in recommendation
        for recommendation in explanation["recommended_next_evidence"]
    )
