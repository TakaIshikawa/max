"""Deterministic risk-aware review gate for buildable ideas."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from max.analysis.thresholds import (
    DEFAULT_APPROVE_THRESHOLD,
    DEFAULT_REJECT_THRESHOLD,
    recommend_review_thresholds,
)
from max.spec.readiness import evaluate_spec_readiness
from max.spec.risk_register import generate_risk_register
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit
from max.types.evaluation import UtilityEvaluation


REVIEW_GATE_SCHEMA_VERSION = "max-review-gate/v1"
ReviewGateDecisionValue = Literal["approve", "needs_revision", "hold", "reject"]

DEFAULT_MIN_READINESS = 75.0
DEFAULT_APPROVE_READINESS = 90.0
DEFAULT_HIGH_BLAST_RADIUS = 75.0
DEFAULT_MEDIUM_BLAST_RADIUS = 55.0


@dataclass(frozen=True)
class ReviewGateEvidence:
    source: str
    status: str
    score: float | None = None
    summary: str = ""
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ReviewGateDecision:
    schema_version: str
    kind: str
    idea_id: str
    title: str
    decision: ReviewGateDecisionValue
    confidence: float
    blocking_reasons: list[str]
    warnings: list[str]
    required_remediations: list[str]
    evidence_used: list[ReviewGateEvidence]


def build_review_gate_decision(
    store: Store,
    idea_id: str,
    profile: dict[str, Any] | None = None,
) -> ReviewGateDecision:
    """Build a deterministic review gate decision for an idea.

    The gate combines persisted utility evaluation and prior-art status with
    deterministic spec readiness, risk-register, threshold, and blast-radius
    analyses. Unknown ideas raise ``ValueError`` so API/CLI callers can map the
    error to their own not-found behavior.
    """
    unit = store.get_buildable_unit(idea_id)
    if unit is None:
        raise ValueError(f"Idea not found: {idea_id}")

    evaluation = store.get_evaluation(idea_id)
    settings = _settings(profile)
    thresholds = _thresholds(store, unit, settings)
    readiness = evaluate_spec_readiness(unit, evaluation)
    risk_register = generate_risk_register(unit, evaluation)
    blast_radius = _blast_radius(unit, evaluation)

    blocking: list[str] = []
    warnings: list[str] = []
    remediations: list[str] = []

    _apply_evaluation_gate(evaluation, thresholds, blocking, warnings, remediations)
    _apply_readiness_gate(readiness, settings, blocking, warnings, remediations)
    _apply_risk_gate(risk_register, blocking, warnings, remediations)
    _apply_prior_art_gate(unit.prior_art_status, blocking, warnings, remediations)
    _apply_blast_radius_gate(blast_radius, settings, blocking, warnings, remediations)

    decision = _decision(evaluation, readiness, blast_radius, thresholds, settings, blocking, warnings)
    return ReviewGateDecision(
        schema_version=REVIEW_GATE_SCHEMA_VERSION,
        kind="max.review_gate",
        idea_id=unit.id,
        title=unit.title,
        decision=decision,
        confidence=_confidence(evaluation, readiness, risk_register, blast_radius, unit.prior_art_status),
        blocking_reasons=list(dict.fromkeys(blocking)),
        warnings=list(dict.fromkeys(warnings)),
        required_remediations=list(dict.fromkeys(remediations)),
        evidence_used=_evidence_used(
            unit,
            evaluation,
            thresholds,
            readiness,
            risk_register,
            blast_radius,
        ),
    )


def _settings(profile: dict[str, Any] | None) -> dict[str, float]:
    source = profile or {}
    return {
        "approve_threshold": float(source.get("approve_threshold", DEFAULT_APPROVE_THRESHOLD)),
        "reject_threshold": float(source.get("reject_threshold", DEFAULT_REJECT_THRESHOLD)),
        "min_readiness": float(source.get("min_readiness", DEFAULT_MIN_READINESS)),
        "approve_readiness": float(source.get("approve_readiness", DEFAULT_APPROVE_READINESS)),
        "high_blast_radius": float(source.get("high_blast_radius", DEFAULT_HIGH_BLAST_RADIUS)),
        "medium_blast_radius": float(source.get("medium_blast_radius", DEFAULT_MEDIUM_BLAST_RADIUS)),
    }


def _thresholds(store: Store, unit: BuildableUnit, settings: dict[str, float]) -> dict[str, Any]:
    recommendations = recommend_review_thresholds(
        store,
        domain=unit.domain or None,
        default_approve_threshold=settings["approve_threshold"],
        default_reject_threshold=settings["reject_threshold"],
    )
    recommendation = recommendations[0] if recommendations else None
    return {
        "approve_threshold": (
            recommendation.approve_threshold if recommendation else settings["approve_threshold"]
        ),
        "reject_threshold": (
            recommendation.reject_threshold if recommendation else settings["reject_threshold"]
        ),
        "source": "history" if recommendation and not recommendation.fallback_used else "fallback",
        "sample_count": recommendation.sample_count if recommendation else 0,
        "reason": recommendation.reason if recommendation else "no feedback history",
    }


def _apply_evaluation_gate(
    evaluation: UtilityEvaluation | None,
    thresholds: dict[str, Any],
    blocking: list[str],
    warnings: list[str],
    remediations: list[str],
) -> None:
    if evaluation is None:
        blocking.append("utility evaluation is missing")
        remediations.append("Run utility evaluation before approval.")
        return

    if evaluation.overall_score <= thresholds["reject_threshold"]:
        blocking.append(
            f"evaluation score {evaluation.overall_score:.1f} is at or below reject threshold "
            f"{thresholds['reject_threshold']:.1f}"
        )
        remediations.append("Improve the weakest evaluation dimensions or reject the idea.")
    elif evaluation.overall_score < thresholds["approve_threshold"]:
        warnings.append(
            f"evaluation score {evaluation.overall_score:.1f} is below approve threshold "
            f"{thresholds['approve_threshold']:.1f}"
        )
        remediations.append("Raise utility score or document an explicit threshold exception.")

    if evaluation.recommendation in {"no", "strong_no"}:
        blocking.append(f"evaluation recommendation is {evaluation.recommendation}")
        remediations.append("Resolve evaluation weaknesses until recommendation improves.")
    elif evaluation.recommendation in {"maybe"}:
        warnings.append("evaluation recommendation is maybe")


def _apply_readiness_gate(
    readiness: dict[str, Any],
    settings: dict[str, float],
    blocking: list[str],
    warnings: list[str],
    remediations: list[str],
) -> None:
    score = float(readiness["score"])
    if score < settings["min_readiness"]:
        blocking.append(
            f"spec readiness {score:.1f} is below minimum {settings['min_readiness']:.1f}"
        )
    elif score < settings["approve_readiness"]:
        warnings.append(
            f"spec readiness {score:.1f} is below approval target {settings['approve_readiness']:.1f}"
        )
    if readiness["failed_check_ids"]:
        remediations.append(str(readiness["remediation"]))


def _apply_risk_gate(
    risk_register: dict[str, Any],
    blocking: list[str],
    warnings: list[str],
    remediations: list[str],
) -> None:
    summary = risk_register["summary"]
    critical_count = int(summary["critical_risk_count"])
    high_count = int(summary["high_risk_count"])
    if critical_count:
        blocking.append(f"{critical_count} critical risk(s) in risk register")
    if high_count >= 4:
        blocking.append(f"{high_count} high risk(s) in risk register")
    elif high_count >= 2:
        warnings.append(f"{high_count} high risk(s) in risk register")

    if critical_count or high_count >= 2:
        for risk in risk_register["risks"][:3]:
            if risk["severity"] in {"critical", "high"} and risk["mitigations"]:
                remediations.append(risk["mitigations"][0])


def _apply_prior_art_gate(
    status: str,
    blocking: list[str],
    warnings: list[str],
    remediations: list[str],
) -> None:
    if status == "strong_match":
        blocking.append("prior art has a strong match")
        remediations.append("Differentiate the idea or reject it as insufficiently novel.")
    elif status == "unchecked":
        blocking.append("prior art check is missing")
        remediations.append("Run prior-art check before approval.")
    elif status == "weak_match":
        warnings.append("prior art has weak matches")
        remediations.append("Document differentiation from weak prior-art matches.")


def _apply_blast_radius_gate(
    blast_radius: dict[str, Any],
    settings: dict[str, float],
    blocking: list[str],
    warnings: list[str],
    remediations: list[str],
) -> None:
    score = float(blast_radius["score"])
    if score >= settings["high_blast_radius"]:
        blocking.append(
            f"blast radius {score:.1f} is high or critical"
        )
    elif score >= settings["medium_blast_radius"]:
        warnings.append(f"blast radius {score:.1f} requires staged review")
    if score >= settings["medium_blast_radius"]:
        for mitigation in blast_radius.get("mitigations", [])[:2]:
            remediations.append(str(mitigation))


def _decision(
    evaluation: UtilityEvaluation | None,
    readiness: dict[str, Any],
    blast_radius: dict[str, Any],
    thresholds: dict[str, Any],
    settings: dict[str, float],
    blocking: list[str],
    warnings: list[str],
) -> ReviewGateDecisionValue:
    if _has_reject_signal(evaluation, thresholds, blocking):
        return "reject"
    if blocking:
        return "hold"
    if warnings:
        return "needs_revision"
    if evaluation is None:
        return "hold"
    if (
        evaluation.overall_score >= thresholds["approve_threshold"]
        and float(readiness["score"]) >= settings["approve_readiness"]
        and float(blast_radius["score"]) < settings["medium_blast_radius"]
    ):
        return "approve"
    return "needs_revision"


def _has_reject_signal(
    evaluation: UtilityEvaluation | None,
    thresholds: dict[str, Any],
    blocking: list[str],
) -> bool:
    if "prior art has a strong match" in blocking:
        return True
    if evaluation is None:
        return False
    return (
        evaluation.overall_score <= thresholds["reject_threshold"]
        or evaluation.recommendation in {"no", "strong_no"}
    )


def _confidence(
    evaluation: UtilityEvaluation | None,
    readiness: dict[str, Any],
    risk_register: dict[str, Any],
    blast_radius: dict[str, Any],
    prior_art_status: str,
) -> float:
    confidence = 0.45
    confidence += min(0.20, float(readiness["score"]) / 100.0 * 0.20)
    confidence += min(0.12, float(blast_radius.get("confidence", 0.5)) * 0.12)
    if risk_register["risks"]:
        confidence += 0.08
    if prior_art_status != "unchecked":
        confidence += 0.08
    if evaluation is not None:
        values = [
            evaluation.pain_severity.confidence,
            evaluation.addressable_scale.confidence,
            evaluation.build_effort.confidence,
            evaluation.composability.confidence,
            evaluation.competitive_density.confidence,
            evaluation.timing_fit.confidence,
            evaluation.compounding_value.confidence,
        ]
        confidence += min(0.17, sum(values) / len(values) * 0.17)
    return round(min(0.95, confidence), 2)


def _evidence_used(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None,
    thresholds: dict[str, Any],
    readiness: dict[str, Any],
    risk_register: dict[str, Any],
    blast_radius: dict[str, Any],
) -> list[ReviewGateEvidence]:
    evaluation_status = "missing" if evaluation is None else evaluation.recommendation
    evaluation_score = None if evaluation is None else round(float(evaluation.overall_score), 1)
    return [
        ReviewGateEvidence(
            source="utility_evaluation",
            status=evaluation_status,
            score=evaluation_score,
            summary="Latest persisted utility evaluation.",
            details={
                "approve_threshold": thresholds["approve_threshold"],
                "reject_threshold": thresholds["reject_threshold"],
                "threshold_source": thresholds["source"],
                "threshold_sample_count": thresholds["sample_count"],
                "threshold_reason": thresholds["reason"],
            },
        ),
        ReviewGateEvidence(
            source="spec_readiness",
            status=str(readiness["status"]),
            score=float(readiness["score"]),
            summary="Deterministic tact-spec readiness checks.",
            details={"failed_check_ids": list(readiness["failed_check_ids"])},
        ),
        ReviewGateEvidence(
            source="risk_register",
            status="generated",
            score=float(risk_register["summary"]["risk_count"]),
            summary="Deterministic risk register severity counts.",
            details={
                "critical_risk_count": risk_register["summary"]["critical_risk_count"],
                "high_risk_count": risk_register["summary"]["high_risk_count"],
                "top_risk_id": risk_register["summary"]["top_risk_id"],
            },
        ),
        ReviewGateEvidence(
            source="prior_art",
            status=unit.prior_art_status,
            score=None,
            summary="Persisted prior-art check status.",
            details={"match_count": len(unit.source_idea_ids)},
        ),
        ReviewGateEvidence(
            source="blast_radius",
            status=str(blast_radius["level"]),
            score=float(blast_radius["score"]),
            summary="Implementation blast-radius estimate.",
            details={
                "affected_surfaces": [
                    surface["name"] if isinstance(surface, dict) else getattr(surface, "name", "")
                    for surface in blast_radius.get("affected_surfaces", [])
                ],
                "fallback_used": bool(blast_radius.get("fallback_used", False)),
            },
        ),
    ]


def _blast_radius(unit: BuildableUnit, evaluation: UtilityEvaluation | None) -> dict[str, Any]:
    try:
        from dataclasses import asdict

        from max.analysis.blast_radius import estimate_idea_blast_radius

        return asdict(estimate_idea_blast_radius(unit, evaluation))
    except Exception:
        score = _fallback_blast_radius_score(unit, evaluation)
        return {
            "score": score,
            "level": _fallback_blast_radius_level(score),
            "confidence": 0.45 if evaluation is None else 0.55,
            "affected_surfaces": [],
            "mitigations": [
                "Define MVP non-goals and validate the riskiest implementation surface first."
            ],
            "fallback_used": True,
        }


def _fallback_blast_radius_score(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None,
) -> float:
    score = 12.0
    score += min(18.0, len(unit.suggested_stack) * 4.0)
    score += min(18.0, len([risk for risk in unit.domain_risks if risk.strip()]) * 6.0)
    score += 12.0 if unit.category in {"application", "automation", "mcp_server"} else 4.0
    if evaluation is None:
        score += 8.0
    elif evaluation.build_effort.value <= 5.0:
        score += 12.0
    elif evaluation.build_effort.value <= 7.0:
        score += 6.0
    return round(min(100.0, score), 1)


def _fallback_blast_radius_level(score: float) -> str:
    if score >= 75.0:
        return "critical"
    if score >= 55.0:
        return "high"
    if score >= 35.0:
        return "medium"
    return "low"
