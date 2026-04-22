"""Deterministic explanations for stored utility evaluations."""

from __future__ import annotations

from collections import Counter
from typing import Any

from max.evaluation.weights import DEFAULT_WEIGHTS
from max.types.buildable_unit import BuildableUnit
from max.types.evaluation import DimensionScore, UtilityEvaluation
from max.types.insight import Insight
from max.types.signal import Signal


DIMENSION_LABELS: dict[str, str] = {
    "pain_severity": "Pain severity",
    "addressable_scale": "Addressable scale",
    "build_effort": "Build effort",
    "composability": "Composability",
    "competitive_density": "Competitive density",
    "timing_fit": "Timing fit",
    "compounding_value": "Compounding value",
}

NEXT_EVIDENCE_BY_DIMENSION: dict[str, str] = {
    "pain_severity": "Collect firsthand problem reports or support/forum threads that show repeated high-cost pain.",
    "addressable_scale": "Collect market-size, install-base, search-volume, or cross-community evidence that the user segment is large enough.",
    "build_effort": "Collect implementation spikes, API feasibility checks, and dependency-risk notes for the MVP path.",
    "composability": "Collect integration evidence from target tool APIs, extension points, and ecosystem workflows.",
    "competitive_density": "Collect prior-art and competitor evidence, including alternatives users already adopt or reject.",
    "timing_fit": "Collect recent trigger evidence such as regulation, platform changes, funding, releases, or adoption inflection points.",
    "compounding_value": "Collect retention, network-effect, reuse, or data-asset evidence showing value improves with usage.",
}

MISSING_FIELD_RULES: tuple[tuple[str, str, float, str], ...] = (
    (
        "specific_user",
        "Specific user",
        3.0,
        "Name the exact persona or role that feels the problem first.",
    ),
    (
        "buyer",
        "Buyer",
        2.0,
        "Identify who can approve or pay for the solution.",
    ),
    (
        "workflow_context",
        "Workflow context",
        2.5,
        "Describe the workflow moment where the idea is used.",
    ),
    (
        "current_workaround",
        "Current workaround",
        1.5,
        "Capture how users solve the problem today and why it fails.",
    ),
    (
        "why_now",
        "Why now",
        1.5,
        "Add the current trigger that makes this newly viable or urgent.",
    ),
    (
        "validation_plan",
        "Validation plan",
        2.5,
        "Define concrete interviews, tests, or acceptance criteria for validation.",
    ),
    (
        "first_10_customers",
        "First 10 customers",
        1.5,
        "List reachable early users or communities to test demand.",
    ),
    (
        "tech_approach",
        "Technical approach",
        1.5,
        "Sketch the MVP implementation path and main dependencies.",
    ),
)


def explain_evaluation(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation,
    *,
    insights: list[Insight] | None = None,
    signals: list[Signal] | None = None,
) -> dict[str, Any]:
    """Explain a stored utility evaluation without model calls."""
    insights = insights or []
    signals = signals or []

    dimensions = _dimension_notes(evaluation)
    top_positive = _top_positive_drivers(dimensions, evaluation)
    top_negative = _top_negative_drivers(dimensions, evaluation)
    evidence_diversity = _evidence_diversity(unit, insights, signals)
    triangulation_hints = _triangulation_hints(evidence_diversity, signals)
    missing_penalties = _missing_field_penalties(unit)
    recommended_next = _recommended_next_evidence(
        dimensions,
        evidence_diversity,
        missing_penalties,
    )

    return {
        "idea_id": unit.id,
        "overall_score": evaluation.overall_score,
        "recommendation": evaluation.recommendation,
        "summary": _summary(evaluation, top_positive, top_negative, missing_penalties),
        "top_positive_drivers": top_positive,
        "top_negative_drivers": top_negative,
        "dimension_notes": dimensions,
        "evidence_diversity": evidence_diversity,
        "triangulation_hints": triangulation_hints,
        "missing_field_penalties": missing_penalties,
        "recommended_next_evidence": recommended_next,
    }


def build_evaluation_explanation(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation,
    *,
    insights: list[Insight] | None = None,
    signals: list[Signal] | None = None,
) -> dict[str, Any]:
    """Compatibility alias for callers that prefer build_* naming."""
    return explain_evaluation(
        unit,
        evaluation,
        insights=insights,
        signals=signals,
    )


def _dimension_notes(evaluation: UtilityEvaluation) -> list[dict[str, Any]]:
    notes: list[dict[str, Any]] = []
    for name in DEFAULT_WEIGHTS:
        score: DimensionScore = getattr(evaluation, name)
        weight = _weight_for(evaluation, name)
        contribution = round(score.value * weight * 10.0, 2)
        notes.append(
            {
                "dimension": name,
                "label": DIMENSION_LABELS[name],
                "score": score.value,
                "confidence": score.confidence,
                "weight": weight,
                "weighted_contribution": contribution,
                "sentiment": _sentiment(score.value, score.confidence),
                "note": score.reasoning,
            }
        )
    return notes


def _top_positive_drivers(
    dimensions: list[dict[str, Any]],
    evaluation: UtilityEvaluation,
) -> list[dict[str, Any]]:
    positive = [
        dim for dim in dimensions if dim["score"] >= 7.0 or dim["weighted_contribution"] >= 10.0
    ]
    positive.sort(
        key=lambda dim: (
            dim["weighted_contribution"],
            dim["score"],
            dim["confidence"],
            dim["dimension"],
        ),
        reverse=True,
    )
    drivers = [_driver(dim, "positive") for dim in positive[:3]]
    for strength in evaluation.strengths[: max(0, 3 - len(drivers))]:
        drivers.append(
            {
                "dimension": "strength",
                "label": "Stored strength",
                "score": None,
                "confidence": None,
                "weight": 0.0,
                "weighted_contribution": 0.0,
                "reason": strength,
            }
        )
    return drivers


def _top_negative_drivers(
    dimensions: list[dict[str, Any]],
    evaluation: UtilityEvaluation,
) -> list[dict[str, Any]]:
    ranked = sorted(
        dimensions,
        key=lambda dim: (
            (10.0 - dim["score"]) * dim["weight"] * 10.0 + (1.0 - dim["confidence"]) * 5.0,
            -dim["score"],
            dim["dimension"],
        ),
        reverse=True,
    )
    negative = [dim for dim in ranked if dim["score"] < 7.0 or dim["confidence"] < 0.6][:3]
    drivers = [_driver(dim, "negative") for dim in negative]
    for weakness in evaluation.weaknesses[: max(0, 3 - len(drivers))]:
        drivers.append(
            {
                "dimension": "weakness",
                "label": "Stored weakness",
                "score": None,
                "confidence": None,
                "weight": 0.0,
                "weighted_contribution": 0.0,
                "reason": weakness,
            }
        )
    return drivers


def _driver(dim: dict[str, Any], polarity: str) -> dict[str, Any]:
    if polarity == "positive":
        reason = (
            f"{dim['label']} scored {dim['score']:.1f}/10 with "
            f"{dim['confidence']:.2f} confidence. {dim['note']}"
        )
    else:
        reason = (
            f"{dim['label']} limited the score at {dim['score']:.1f}/10 "
            f"with {dim['confidence']:.2f} confidence. {dim['note']}"
        )
    return {
        "dimension": dim["dimension"],
        "label": dim["label"],
        "score": dim["score"],
        "confidence": dim["confidence"],
        "weight": dim["weight"],
        "weighted_contribution": dim["weighted_contribution"],
        "reason": reason,
    }


def _evidence_diversity(
    unit: BuildableUnit,
    insights: list[Insight],
    signals: list[Signal],
) -> dict[str, Any]:
    sources = sorted({signal.source_adapter for signal in signals if signal.source_adapter})
    source_types = sorted(
        {
            signal.source_type.value
            if hasattr(signal.source_type, "value")
            else str(signal.source_type)
            for signal in signals
            if signal.source_type
        }
    )
    roles = Counter(signal.signal_role or "unknown" for signal in signals)
    avg_credibility = (
        round(sum(signal.credibility for signal in signals) / len(signals), 3) if signals else 0.0
    )
    evidence_types = {
        "insights": len(unit.inspiring_insights),
        "signals": len(unit.evidence_signals),
        "source_ideas": len(unit.source_idea_ids),
        "rationale": 1 if _meaningful(unit.evidence_rationale, min_words=4) else 0,
    }
    diversity_score = _evidence_diversity_score(
        signal_count=len(signals),
        source_count=len(sources),
        evidence_type_count=sum(1 for count in evidence_types.values() if count > 0),
        avg_credibility=avg_credibility,
    )
    return {
        "signal_count": len(signals),
        "insight_count": len(insights),
        "source_count": len(sources),
        "sources": sources,
        "source_types": source_types,
        "signal_roles": dict(sorted(roles.items())),
        "avg_credibility": avg_credibility,
        "evidence_types": evidence_types,
        "diversity_score": diversity_score,
        "note": _evidence_note(len(signals), len(insights), sources, source_types),
    }


def _triangulation_hints(
    evidence_diversity: dict[str, Any],
    signals: list[Signal],
) -> list[str]:
    hints: list[str] = []
    signal_count = evidence_diversity["signal_count"]
    source_count = evidence_diversity["source_count"]
    roles = evidence_diversity["signal_roles"]
    source_types = evidence_diversity["source_types"]

    if signal_count == 0:
        hints.append(
            "No linked signals are available; add primary evidence before trusting the score."
        )
    elif source_count >= 3:
        hints.append(
            f"Evidence is triangulated across {source_count} adapters: {', '.join(evidence_diversity['sources'])}."
        )
    elif source_count == 2:
        hints.append(
            "Evidence has two-source support; add one more independent source to reduce source bias."
        )
    else:
        hints.append(
            "Evidence comes from a single source; add independent corroboration from another adapter."
        )

    if len(source_types) >= 2:
        hints.append(f"Source types cover {', '.join(source_types)}, which improves diversity.")
    else:
        hints.append(
            "Collect a different source type, such as forum pain, registry adoption, funding, security, or roadmap evidence."
        )

    if len([role for role, count in roles.items() if role != "unknown" and count > 0]) >= 2:
        role_text = ", ".join(
            f"{role}={count}" for role, count in sorted(roles.items()) if role != "unknown"
        )
        hints.append(f"Signal roles cover multiple angles: {role_text}.")
    elif signals:
        hints.append(
            "Tag or collect signals that separately cover problem, market, and solution evidence."
        )

    return hints


def _missing_field_penalties(unit: BuildableUnit) -> list[dict[str, Any]]:
    penalties: list[dict[str, Any]] = []
    for field, label, penalty, remediation in MISSING_FIELD_RULES:
        value = getattr(unit, field, "")
        if not _meaningful(value, min_words=2):
            severity = "high" if penalty >= 2.5 else "medium"
            penalties.append(
                {
                    "field": field,
                    "label": label,
                    "severity": severity,
                    "penalty": penalty,
                    "note": remediation,
                }
            )
    if not unit.inspiring_insights and not unit.evidence_signals and not unit.evidence_rationale:
        penalties.append(
            {
                "field": "evidence",
                "label": "Evidence",
                "severity": "high",
                "penalty": 3.0,
                "note": "Attach at least one insight, signal, or evidence rationale before relying on the evaluation.",
            }
        )
    return sorted(penalties, key=lambda item: (-item["penalty"], item["field"]))


def _recommended_next_evidence(
    dimensions: list[dict[str, Any]],
    evidence_diversity: dict[str, Any],
    missing_penalties: list[dict[str, Any]],
) -> list[str]:
    recommendations: list[str] = []

    weak_dimensions = sorted(
        dimensions,
        key=lambda dim: (
            dim["score"],
            dim["confidence"],
            -dim["weight"],
            dim["dimension"],
        ),
    )
    for dim in weak_dimensions:
        if dim["score"] < 7.0 or dim["confidence"] < 0.65:
            recommendations.append(NEXT_EVIDENCE_BY_DIMENSION[dim["dimension"]])
        if len(recommendations) >= 3:
            break

    if evidence_diversity["source_count"] < 2:
        recommendations.append(
            "Add corroborating evidence from at least one independent source adapter."
        )
    if evidence_diversity["signal_count"] < 3:
        recommendations.append(
            "Attach at least three concrete signals so confidence is not driven by a single example."
        )

    missing_by_field = {item["field"]: item for item in missing_penalties}
    for field in ("specific_user", "buyer", "workflow_context", "validation_plan"):
        if field in missing_by_field:
            recommendations.append(missing_by_field[field]["note"])

    deduped: list[str] = []
    for recommendation in recommendations:
        if recommendation not in deduped:
            deduped.append(recommendation)
    return deduped[:5]


def _summary(
    evaluation: UtilityEvaluation,
    top_positive: list[dict[str, Any]],
    top_negative: list[dict[str, Any]],
    missing_penalties: list[dict[str, Any]],
) -> str:
    positive = top_positive[0]["label"].lower() if top_positive else "the stored strengths"
    negative = top_negative[0]["label"].lower() if top_negative else "no major dimension"
    missing_count = len(missing_penalties)
    missing_text = (
        f" and {missing_count} missing-field penalty{'' if missing_count == 1 else 's'}"
        if missing_count
        else ""
    )
    return (
        f"The current {evaluation.recommendation} recommendation is driven mainly by "
        f"{positive}, while {negative} is the main limiter{missing_text}."
    )


def _weight_for(evaluation: UtilityEvaluation, dimension: str) -> float:
    weight = evaluation.weights_used.get(dimension)
    if isinstance(weight, (int, float)):
        return float(weight)
    return DEFAULT_WEIGHTS[dimension]


def _sentiment(score: float, confidence: float) -> str:
    if score >= 7.5 and confidence >= 0.6:
        return "positive"
    if score < 6.0 or confidence < 0.5:
        return "negative"
    return "mixed"


def _meaningful(value: object, *, min_words: int) -> bool:
    if not isinstance(value, str):
        return bool(value)
    clean = value.strip()
    if not clean:
        return False
    words = [word for word in clean.split() if word]
    return len(words) >= min_words and len(clean) >= 8


def _evidence_diversity_score(
    *,
    signal_count: int,
    source_count: int,
    evidence_type_count: int,
    avg_credibility: float,
) -> float:
    signal_component = min(signal_count / 3.0, 1.0) * 0.30
    source_component = min(source_count / 3.0, 1.0) * 0.30
    type_component = min(evidence_type_count / 3.0, 1.0) * 0.20
    credibility_component = max(0.0, min(avg_credibility, 1.0)) * 0.20
    return round(
        (signal_component + source_component + type_component + credibility_component) * 100.0,
        1,
    )


def _evidence_note(
    signal_count: int,
    insight_count: int,
    sources: list[str],
    source_types: list[str],
) -> str:
    if signal_count == 0 and insight_count == 0:
        return "No resolved evidence is linked to this idea."
    source_text = ", ".join(sources) if sources else "no resolved signal adapters"
    type_text = ", ".join(source_types) if source_types else "no source types"
    return (
        f"Resolved {signal_count} signal(s) and {insight_count} insight(s) "
        f"from {source_text}; source types: {type_text}."
    )
