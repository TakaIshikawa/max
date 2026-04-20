"""Critique and score draft ideas before formal evaluation."""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from max.ideation.evidence import EvidencePack
from max.llm.client import structured_call
from max.types.buildable_unit import BuildableUnit


class IdeaCritique(BaseModel):
    """Quality-loop critique for a single idea."""

    title: str
    urgency: float = 0.0
    buyer_clarity: float = 0.0
    specificity: float = 0.0
    evidence_support: float = 0.0
    feasibility: float = 0.0
    differentiation: float = 0.0
    distribution_path: float = 0.0
    domain_risk: float = 0.0
    novelty: float = 0.0
    usefulness: float = 0.0
    reasoning: str = ""
    rejection_tags: list[str] = Field(default_factory=list)

    @property
    def quality_score(self) -> float:
        values = [
            self.urgency,
            self.buyer_clarity,
            self.specificity,
            self.evidence_support,
            self.feasibility,
            self.differentiation,
            self.distribution_path,
            self.domain_risk,
            self.novelty,
            self.usefulness,
        ]
        return sum(values) / len(values)


class CritiqueOutput(BaseModel):
    critiques: list[IdeaCritique]


def _units_json(units: list[BuildableUnit]) -> str:
    return json.dumps(
        [
            {
                "title": u.title,
                "one_liner": u.one_liner,
                "problem": u.problem,
                "solution": u.solution,
                "specific_user": u.specific_user,
                "buyer": u.buyer,
                "workflow_context": u.workflow_context,
                "current_workaround": u.current_workaround,
                "why_now": u.why_now,
                "validation_plan": u.validation_plan,
                "evidence_rationale": u.evidence_rationale,
            }
            for u in units
        ],
        indent=2,
    )


def _prompt(units: list[BuildableUnit], evidence_pack: EvidencePack) -> str:
    return f"""\
Critique these draft ideas against the domain evidence pack.

Score each dimension from 0-10:
- urgency: severity and frequency of the problem
- buyer_clarity: whether a specific economic buyer is named
- specificity: whether the user, workflow moment, and current workaround are concrete
- evidence_support: whether claims trace to supplied evidence
- feasibility: whether a focused MVP is buildable
- differentiation: whether this avoids generic or crowded patterns
- distribution_path: whether first customers are reachable
- domain_risk: higher means manageable risk and constraints
- novelty: meaningfully different from obvious solutions
- usefulness: likelihood the target user would care

Use rejection_tags when applicable:
no_clear_buyer, generic_ai_assistant, weak_evidence, impossible_data_access,
low_willingness_to_pay, too_broad, unclear_workflow, high_domain_risk.

EVIDENCE PACK:
{evidence_pack.to_json()}

DRAFT IDEAS:
{_units_json(units)}
"""


def critique_ideas(
    units: list[BuildableUnit],
    evidence_pack: EvidencePack,
) -> list[IdeaCritique]:
    """Run LLM critique for draft ideas."""
    if not units:
        return []

    result = structured_call(
        system=(
            "You are a strict domain-focused product critic. "
            "Reward evidence-backed, buyer-specific, testable ideas. "
            "Penalize generic assistants, vague dashboards, and ideas without a buyer."
        ),
        prompt=_prompt(units, evidence_pack),
        output_type=CritiqueOutput,
        temperature=0.2,
        stage="ideation_critique",
    )
    return result.critiques


def apply_critiques(
    units: list[BuildableUnit],
    critiques: list[IdeaCritique],
) -> list[BuildableUnit]:
    """Copy critique scores and tags onto matching units."""
    by_title = {c.title.lower(): c for c in critiques}
    for unit in units:
        critique = by_title.get(unit.title.lower())
        if not critique:
            continue
        unit.novelty_score = max(0.0, min(10.0, critique.novelty))
        unit.usefulness_score = max(0.0, min(10.0, critique.usefulness))
        unit.quality_score = max(0.0, min(10.0, critique.quality_score))
        unit.rejection_tags = critique.rejection_tags
    return units


def critique_to_record(critique: IdeaCritique) -> dict:
    """Convert critique model to a persistence-friendly dict."""
    data = critique.model_dump()
    data["quality_score"] = critique.quality_score
    return data
