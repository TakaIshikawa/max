"""Synthesis engine — transforms signals into insights via LLM."""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from max.llm.client import structured_call
from max.synthesis.prompts import SYSTEM, build_incremental_synthesis_prompt, build_synthesis_prompt
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


def synthesize(
    signals: list[Signal],
    *,
    prior_insights: list[Insight] | None = None,
    cluster_context: str | None = None,
) -> list[Insight]:
    """Synthesize a batch of signals into insights.

    When prior_insights is provided, uses an incremental prompt that instructs
    the LLM to generate only new insights that complement the existing ones.
    When cluster_context is provided, includes cross-source corroboration info.
    """
    if not signals:
        return []

    signals_json = json.dumps(
        [
            {
                "id": s.id,
                "source_type": s.source_type.value,
                "signal_role": s.signal_role,
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

    if prior_insights:
        prior_json = json.dumps(
            [
                {
                    "title": ins.title,
                    "summary": ins.summary,
                    "category": ins.category.value,
                    "domains": ins.domains,
                    "time_horizon": ins.time_horizon,
                }
                for ins in prior_insights
            ],
            indent=2,
        )
        prompt = build_incremental_synthesis_prompt(
            signals_json, prior_json, cluster_context=cluster_context,
        )
    else:
        prompt = build_synthesis_prompt(signals_json, cluster_context=cluster_context)

    result = structured_call(
        system=SYSTEM,
        prompt=prompt,
        output_type=SynthesisOutput,
        stage="synthesis",
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
