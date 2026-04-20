"""Revise draft ideas using critique and domain evidence."""

from __future__ import annotations

import json

from pydantic import BaseModel

from max.ideation.critique import IdeaCritique
from max.ideation.evidence import EvidencePack
from max.ideation.engine import BuildableUnitOutput, IdeationOutput, _parse_output
from max.llm.client import structured_call
from max.types.buildable_unit import BuildableUnit, IdeationMode
from max.types.insight import Insight


class RevisionInput(BaseModel):
    idea: dict
    critique: dict | None = None


def _revision_payload(
    units: list[BuildableUnit],
    critiques: list[IdeaCritique],
) -> str:
    by_title = {c.title.lower(): c for c in critiques}
    payload = []
    for unit in units:
        critique = by_title.get(unit.title.lower())
        payload.append(
            RevisionInput(
                idea={
                    "title": unit.title,
                    "one_liner": unit.one_liner,
                    "category": unit.category,
                    "problem": unit.problem,
                    "solution": unit.solution,
                    "target_users": unit.target_users,
                    "value_proposition": unit.value_proposition,
                    "specific_user": unit.specific_user,
                    "buyer": unit.buyer,
                    "workflow_context": unit.workflow_context,
                    "current_workaround": unit.current_workaround,
                    "why_now": unit.why_now,
                    "validation_plan": unit.validation_plan,
                    "first_10_customers": unit.first_10_customers,
                    "domain_risks": unit.domain_risks,
                    "evidence_rationale": unit.evidence_rationale,
                    "inspiring_insights": unit.inspiring_insights,
                    "tech_approach": unit.tech_approach,
                    "suggested_stack": unit.suggested_stack,
                    "composability_notes": unit.composability_notes,
                },
                critique=critique.model_dump() if critique else None,
            ).model_dump()
        )
    return json.dumps(payload, indent=2)


def revise_ideas(
    units: list[BuildableUnit],
    critiques: list[IdeaCritique],
    evidence_pack: EvidencePack,
    insights: list[Insight],
) -> list[BuildableUnit]:
    """Revise draft ideas to address critique findings."""
    if not units:
        return []

    result = structured_call(
        system=(
            "You revise product ideas into specific, evidence-backed, buyer-clear "
            "buildable units. Preserve useful evidence links. Drop ideas that cannot "
            "be made concrete."
        ),
        prompt=f"""\
Revise these ideas using the critique and evidence pack.

For every returned idea, include all fields in this schema:
{BuildableUnitOutput.model_json_schema()}

EVIDENCE PACK:
{evidence_pack.to_json()}

IDEAS WITH CRITIQUES:
{_revision_payload(units, critiques)}
""",
        output_type=IdeationOutput,
        temperature=0.4,
        stage="ideation_revision",
    )
    return _parse_output(result, insights, IdeationMode.REFINEMENT)
