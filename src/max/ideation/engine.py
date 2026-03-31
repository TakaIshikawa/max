"""Ideation engine — transforms insights into buildable units via LLM."""

from __future__ import annotations

import json
from itertools import combinations

from pydantic import BaseModel, Field

from max.llm.client import structured_call
from max.ideation.prompts import (
    SYSTEM,
    build_cross_domain_prompt,
    build_ideation_prompt,
    build_refinement_prompt,
)
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


def _insights_to_json(insights: list[Insight]) -> str:
    return json.dumps(
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


def _units_to_json(units: list[BuildableUnit]) -> str:
    return json.dumps(
        [
            {
                "id": u.id,
                "title": u.title,
                "one_liner": u.one_liner,
                "category": u.category.value,
                "problem": u.problem,
                "solution": u.solution,
                "target_users": u.target_users,
                "value_proposition": u.value_proposition,
                "tech_approach": u.tech_approach,
                "composability_notes": u.composability_notes,
            }
            for u in units
        ],
        indent=2,
    )


def _parse_output(
    result: IdeationOutput,
    insights: list[Insight],
    mode: IdeationMode,
) -> list[BuildableUnit]:
    """Convert LLM output to BuildableUnit list with evidence tracing."""
    insight_map = {i.id: i for i in insights}
    units: list[BuildableUnit] = []

    for out in result.ideas:
        try:
            category = BuildableCategory(out.category)
        except ValueError:
            category = BuildableCategory.APPLICATION

        evidence_signals: list[str] = []
        for ins_id in out.inspiring_insights:
            if ins_id in insight_map:
                evidence_signals.extend(insight_map[ins_id].evidence)

        units.append(
            BuildableUnit(
                title=out.title,
                one_liner=out.one_liner,
                category=category,
                ideation_mode=mode,
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


def _format_existing_ideas(units: list[BuildableUnit]) -> str | None:
    """Compact '- Title: one_liner' list for prompt injection."""
    if not units:
        return None
    lines = [f"- {u.title}: {u.one_liner}" for u in units]
    return "\n".join(lines)


def ideate(
    insights: list[Insight],
    *,
    existing_ideas: list[BuildableUnit] | None = None,
    gaps_context: str | None = None,
    learned_context: str | None = None,
) -> list[BuildableUnit]:
    """Generate buildable unit ideas from insights (direct mode)."""
    if not insights:
        return []

    existing_text = _format_existing_ideas(existing_ideas) if existing_ideas else None

    result = structured_call(
        system=SYSTEM,
        prompt=build_ideation_prompt(
            _insights_to_json(insights),
            existing_ideas_text=existing_text,
            gaps_text=gaps_context,
            learned_context=learned_context,
        ),
        output_type=IdeationOutput,
        stage="ideation",
    )

    return _parse_output(result, insights, IdeationMode.DIRECT)


def ideate_refinement(
    existing_units: list[BuildableUnit],
    new_insights: list[Insight],
) -> list[BuildableUnit]:
    """Refine existing ideas based on new insights."""
    if not existing_units or not new_insights:
        return []

    result = structured_call(
        system=SYSTEM,
        prompt=build_refinement_prompt(
            _units_to_json(existing_units),
            _insights_to_json(new_insights),
        ),
        output_type=IdeationOutput,
        stage="ideation_refinement",
    )

    return _parse_output(result, new_insights, IdeationMode.REFINEMENT)


def ideate_cross_domain(
    insights: list[Insight],
    *,
    existing_ideas: list[BuildableUnit] | None = None,
    gaps_context: str | None = None,
    learned_context: str | None = None,
) -> list[BuildableUnit]:
    """Generate ideas by combining insights from different domains."""
    if not insights:
        return []

    # Group insights by domain
    domain_groups: dict[str, list[Insight]] = {}
    for ins in insights:
        for domain in ins.domains:
            domain_groups.setdefault(domain, []).append(ins)

    domains = list(domain_groups.keys())
    if len(domains) < 2:
        return []

    existing_text = _format_existing_ideas(existing_ideas) if existing_ideas else None
    all_units: list[BuildableUnit] = []

    # Take up to 3 domain pairs to avoid too many LLM calls
    for domain_a, domain_b in list(combinations(domains, 2))[:3]:
        result = structured_call(
            system=SYSTEM,
            prompt=build_cross_domain_prompt(
                _insights_to_json(domain_groups[domain_a]),
                _insights_to_json(domain_groups[domain_b]),
                existing_ideas_text=existing_text,
                gaps_text=gaps_context,
                learned_context=learned_context,
            ),
            output_type=IdeationOutput,
            stage="ideation_cross_domain",
        )

        all_insights = domain_groups[domain_a] + domain_groups[domain_b]
        all_units.extend(_parse_output(result, all_insights, IdeationMode.CROSS_DOMAIN))

    return all_units
