"""Generate tact-compatible project specs from buildable ideas."""

from __future__ import annotations

from typing import Any

from max.spec.stakeholder_handoff import generate_stakeholder_handoff
from max.types.buildable_unit import BuildableUnit
from max.types.evaluation import UtilityEvaluation


SPEC_PREVIEW_SCHEMA_VERSION = "tact-spec-preview/v1"


def generate_spec_preview(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None = None,
) -> dict[str, Any]:
    """Map a buildable unit and optional evaluation into a serializable spec."""
    spec = {
        "schema_version": SPEC_PREVIEW_SCHEMA_VERSION,
        "kind": "tact.project_spec",
        "source": {
            "system": "max",
            "type": "idea",
            "idea_id": unit.id,
            "status": unit.status,
            "domain": unit.domain,
            "category": unit.category,
            "created_at": unit.created_at.isoformat(),
            "updated_at": unit.updated_at.isoformat(),
        },
        "project": {
            "title": unit.title,
            "summary": unit.one_liner,
            "value_proposition": unit.value_proposition,
            "target_users": unit.target_users,
            "specific_user": unit.specific_user,
            "buyer": unit.buyer,
            "workflow_context": unit.workflow_context,
        },
        "problem": {
            "statement": unit.problem,
            "current_workaround": unit.current_workaround,
            "why_now": unit.why_now,
        },
        "solution": {
            "approach": unit.solution,
            "technical_approach": unit.tech_approach,
            "suggested_stack": unit.suggested_stack,
            "composability_notes": unit.composability_notes,
        },
        "execution": {
            "mvp_scope": _mvp_scope(unit),
            "first_10_customers": unit.first_10_customers,
            "validation_plan": unit.validation_plan,
            "risks": unit.domain_risks,
        },
        "evidence": {
            "rationale": unit.evidence_rationale,
            "insight_ids": unit.inspiring_insights,
            "signal_ids": unit.evidence_signals,
            "source_idea_ids": unit.source_idea_ids,
        },
        "quality": {
            "quality_score": unit.quality_score,
            "novelty_score": unit.novelty_score,
            "usefulness_score": unit.usefulness_score,
            "rejection_tags": unit.rejection_tags,
        },
        "evaluation": _evaluation_payload(evaluation),
    }
    spec["artifacts"] = {
        "stakeholder_handoff": generate_stakeholder_handoff(unit, evaluation, spec)
    }
    return spec


def _mvp_scope(unit: BuildableUnit) -> list[str]:
    scope = [
        unit.solution,
        unit.tech_approach,
        unit.validation_plan,
    ]
    return [item for item in scope if item]


def _evaluation_payload(evaluation: UtilityEvaluation | None) -> dict[str, Any] | None:
    if evaluation is None:
        return None

    return {
        "overall_score": evaluation.overall_score,
        "rank": evaluation.rank,
        "recommendation": evaluation.recommendation,
        "strengths": evaluation.strengths,
        "weaknesses": evaluation.weaknesses,
        "weights_used": evaluation.weights_used,
        "dimensions": {
            name: _dimension_payload(getattr(evaluation, name))
            for name in (
                "pain_severity",
                "addressable_scale",
                "build_effort",
                "composability",
                "competitive_density",
                "timing_fit",
                "compounding_value",
            )
        },
    }


def _dimension_payload(score) -> dict[str, Any]:
    return {
        "value": score.value,
        "confidence": score.confidence,
        "reasoning": score.reasoning,
    }
