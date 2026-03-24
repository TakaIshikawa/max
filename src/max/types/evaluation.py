"""UtilityEvaluation — 7-dimension scoring for a BuildableUnit."""

from __future__ import annotations

from pydantic import BaseModel, Field


class DimensionScore(BaseModel):
    value: float  # 0-10
    confidence: float  # 0-1
    reasoning: str


class UtilityEvaluation(BaseModel):
    buildable_unit_id: str

    # 7 utility dimensions
    pain_severity: DimensionScore
    addressable_scale: DimensionScore
    build_effort: DimensionScore  # INVERTED: lower effort = higher score
    composability: DimensionScore
    competitive_density: DimensionScore  # INVERTED: fewer competitors = higher score
    timing_fit: DimensionScore
    compounding_value: DimensionScore

    # Composite
    overall_score: float = 0.0  # 0-100
    rank: int | None = None

    # Qualitative
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    recommendation: str = "maybe"  # strong_yes | yes | maybe | no | strong_no

    weights_used: dict[str, float] = Field(default_factory=dict)
