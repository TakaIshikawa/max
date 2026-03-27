"""Evaluation engine — scores buildable units on 7 dimensions."""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from max.evaluation.prompts import SYSTEM, build_evaluation_prompt
from max.evaluation.weights import DEFAULT_WEIGHTS, compute_overall_score
from max.llm.client import structured_call
from max.types.buildable_unit import BuildableUnit
from max.types.evaluation import DimensionScore, UtilityEvaluation


class DimensionScoreOutput(BaseModel):
    value: float
    confidence: float
    reasoning: str


class EvaluationOutput(BaseModel):
    pain_severity: DimensionScoreOutput
    addressable_scale: DimensionScoreOutput
    build_effort: DimensionScoreOutput
    composability: DimensionScoreOutput
    competitive_density: DimensionScoreOutput
    timing_fit: DimensionScoreOutput
    compounding_value: DimensionScoreOutput
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    recommendation: str = "maybe"


def evaluate(
    unit: BuildableUnit,
    *,
    weights: dict[str, float] | None = None,
    evidence: str | None = None,
) -> UtilityEvaluation:
    """Evaluate a single buildable unit across 7 dimensions."""
    unit_json = json.dumps(
        {
            "id": unit.id,
            "title": unit.title,
            "one_liner": unit.one_liner,
            "category": unit.category.value,
            "problem": unit.problem,
            "solution": unit.solution,
            "target_users": unit.target_users,
            "value_proposition": unit.value_proposition,
            "tech_approach": unit.tech_approach,
            "composability_notes": unit.composability_notes,
        },
        indent=2,
    )

    result = structured_call(
        system=SYSTEM,
        prompt=build_evaluation_prompt(unit_json, evidence_json=evidence),
        output_type=EvaluationOutput,
        temperature=0.3,  # Lower temperature for more consistent scoring
        stage="evaluation",
    )

    def to_score(out: DimensionScoreOutput) -> DimensionScore:
        return DimensionScore(
            value=max(0.0, min(10.0, out.value)),
            confidence=max(0.0, min(1.0, out.confidence)),
            reasoning=out.reasoning,
        )

    pain = to_score(result.pain_severity)
    scale = to_score(result.addressable_scale)
    effort = to_score(result.build_effort)
    comp = to_score(result.composability)
    density = to_score(result.competitive_density)
    timing = to_score(result.timing_fit)
    compound = to_score(result.compounding_value)

    dimension_values = {
        "pain_severity": pain.value,
        "addressable_scale": scale.value,
        "build_effort": effort.value,
        "composability": comp.value,
        "competitive_density": density.value,
        "timing_fit": timing.value,
        "compounding_value": compound.value,
    }

    effective_weights = weights or DEFAULT_WEIGHTS
    overall = compute_overall_score(dimension_values, effective_weights)

    valid_recs = {"strong_yes", "yes", "maybe", "no", "strong_no"}
    rec = result.recommendation if result.recommendation in valid_recs else "maybe"

    return UtilityEvaluation(
        buildable_unit_id=unit.id,
        pain_severity=pain,
        addressable_scale=scale,
        build_effort=effort,
        composability=comp,
        competitive_density=density,
        timing_fit=timing,
        compounding_value=compound,
        overall_score=overall,
        strengths=result.strengths,
        weaknesses=result.weaknesses,
        recommendation=rec,
        weights_used=effective_weights,
    )
