"""Synthesis engine — transforms signals into insights via LLM."""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from max.llm.client import structured_call
from max.synthesis.prompts import SYSTEM, build_synthesis_prompt
from max.types.insight import Insight, InsightCategory
from max.types.signal import Signal


class InsightOutput(BaseModel):
    """LLM output schema for a single insight."""

    category: str
    title: str
    summary: str
    evidence: list[str] = Field(default_factory=list)
    confidence: float = 0.5
    domains: list[str] = Field(default_factory=list)
    implications: list[str] = Field(default_factory=list)
    time_horizon: str = "near_term"


class SynthesisOutput(BaseModel):
    """LLM output schema for batch of insights."""

    insights: list[InsightOutput]


def synthesize(signals: list[Signal]) -> list[Insight]:
    """Synthesize a batch of signals into insights."""
    if not signals:
        return []

    signals_json = json.dumps(
        [
            {
                "id": s.id,
                "source_type": s.source_type.value,
                "title": s.title,
                "content": s.content[:500],
                "tags": s.tags,
                "credibility": s.credibility,
                "url": s.url,
            }
            for s in signals
        ],
        indent=2,
    )

    result = structured_call(
        system=SYSTEM,
        prompt=build_synthesis_prompt(signals_json),
        output_type=SynthesisOutput,
    )

    insights: list[Insight] = []
    for out in result.insights:
        try:
            category = InsightCategory(out.category)
        except ValueError:
            category = InsightCategory.EMERGING_PATTERN

        insights.append(
            Insight(
                category=category,
                title=out.title,
                summary=out.summary,
                evidence=out.evidence,
                confidence=max(0.0, min(1.0, out.confidence)),
                domains=out.domains,
                implications=out.implications,
                time_horizon=out.time_horizon
                if out.time_horizon in ("near_term", "medium_term", "long_term")
                else "near_term",
            )
        )

    return insights
