"""Ideation engine — transforms insights into buildable units via LLM."""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from max.llm.client import structured_call
from max.ideation.prompts import SYSTEM, build_ideation_prompt
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode
from max.types.insight import Insight


class BuildableUnitOutput(BaseModel):
    """LLM output schema for a single idea."""

    title: str
    one_liner: str
    category: str
    problem: str
    solution: str
    target_users: str = "both"
    value_proposition: str
    inspiring_insights: list[str] = Field(default_factory=list)
    tech_approach: str = ""
    suggested_stack: dict = Field(default_factory=dict)
    composability_notes: str = ""


class IdeationOutput(BaseModel):
    """LLM output schema for batch of ideas."""

    ideas: list[BuildableUnitOutput]


def ideate(insights: list[Insight]) -> list[BuildableUnit]:
    """Generate buildable unit ideas from insights."""
    if not insights:
        return []

    insights_json = json.dumps(
        [
            {
                "id": i.id,
                "category": i.category.value,
                "title": i.title,
                "summary": i.summary,
                "confidence": i.confidence,
                "domains": i.domains,
                "implications": i.implications,
                "time_horizon": i.time_horizon,
            }
            for i in insights
        ],
        indent=2,
    )

    result = structured_call(
        system=SYSTEM,
        prompt=build_ideation_prompt(insights_json),
        output_type=IdeationOutput,
    )

    units: list[BuildableUnit] = []
    for out in result.ideas:
        try:
            category = BuildableCategory(out.category)
        except ValueError:
            category = BuildableCategory.APPLICATION

        # Collect signal IDs transitively from inspiring insights
        insight_map = {i.id: i for i in insights}
        evidence_signals: list[str] = []
        for ins_id in out.inspiring_insights:
            if ins_id in insight_map:
                evidence_signals.extend(insight_map[ins_id].evidence)

        units.append(
            BuildableUnit(
                title=out.title,
                one_liner=out.one_liner,
                category=category,
                ideation_mode=IdeationMode.DIRECT,
                problem=out.problem,
                solution=out.solution,
                target_users=out.target_users
                if out.target_users in ("humans", "agents", "both")
                else "both",
                value_proposition=out.value_proposition,
                inspiring_insights=out.inspiring_insights,
                evidence_signals=list(set(evidence_signals)),
                tech_approach=out.tech_approach,
                suggested_stack=out.suggested_stack,
                composability_notes=out.composability_notes,
            )
        )

    return units
