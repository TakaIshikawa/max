"""Insight — LLM-synthesized pattern from signals."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field


class InsightCategory(StrEnum):
    PAIN_POINT = "pain_point"
    GAP = "gap"
    TREND = "trend"
    VULNERABILITY = "vulnerability"
    CONVERGENCE = "convergence"
    EMERGING_PATTERN = "emerging_pattern"


class Insight(BaseModel):
    id: str = Field(default="")
    category: InsightCategory
    title: str
    summary: str
    evidence: list[str] = Field(default_factory=list)  # Signal IDs
    confidence: float = 0.5
    domains: list[str] = Field(default_factory=list)
    implications: list[str] = Field(default_factory=list)
    time_horizon: str = "near_term"  # near_term | medium_term | long_term
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
