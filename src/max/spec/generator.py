"""Spec generator — transforms evaluated buildable units into tact specs."""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from max.llm.client import structured_call
from max.spec.prompts import SYSTEM, build_spec_prompt
from max.types.buildable_unit import BuildableUnit
from max.types.evaluation import UtilityEvaluation
from max.types.tact_spec import (
    TactArchitecturalDecision,
    TactArchitecturalPattern,
    TactArchitecture,
    TactGoal,
    TactProduct,
    TactRequirement,
    TactSpec,
    TactTechStack,
)


class GoalOutput(BaseModel):
    id: str
    description: str
    success_criteria: str


class TechStackOutput(BaseModel):
    languages: list[str] = Field(default_factory=list)
    frameworks: list[str] = Field(default_factory=list)
    infrastructure: list[str] = Field(default_factory=list)


class PatternOutput(BaseModel):
    name: str
    description: str
    scope: list[str] = Field(default_factory=list)


class DecisionOutput(BaseModel):
    id: str
    title: str
    decision: str
    rationale: str


class RequirementOutput(BaseModel):
    title: str
    priority: str = "medium"
    description: str = ""
    acceptance_criteria: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)


class SpecOutput(BaseModel):
    name: str
    vision: str
    goals: list[GoalOutput] = Field(default_factory=list)
    tech_stack: TechStackOutput = Field(default_factory=TechStackOutput)
    constraints: list[str] = Field(default_factory=list)
    patterns: list[PatternOutput] = Field(default_factory=list)
    invariants: list[str] = Field(default_factory=list)
    conventions: list[str] = Field(default_factory=list)
    decisions: list[DecisionOutput] = Field(default_factory=list)
    requirements: list[RequirementOutput] = Field(default_factory=list)


def generate_spec(unit: BuildableUnit, evaluation: UtilityEvaluation) -> TactSpec:
    """Generate a tact-compatible spec from a buildable unit and its evaluation."""
    unit_json = json.dumps(
        {
            "id": unit.id,
            "title": unit.title,
            "one_liner": unit.one_liner,
            "category": unit.category,
            "problem": unit.problem,
            "solution": unit.solution,
            "target_users": unit.target_users,
            "value_proposition": unit.value_proposition,
            "tech_approach": unit.tech_approach,
            "suggested_stack": unit.suggested_stack,
            "composability_notes": unit.composability_notes,
        },
        indent=2,
    )

    eval_json = json.dumps(
        {
            "overall_score": evaluation.overall_score,
            "strengths": evaluation.strengths,
            "weaknesses": evaluation.weaknesses,
            "recommendation": evaluation.recommendation,
        },
        indent=2,
    )

    result = structured_call(
        system=SYSTEM,
        prompt=build_spec_prompt(unit_json, eval_json),
        output_type=SpecOutput,
        temperature=0.4,
        stage="spec_generation",
    )

    product = TactProduct(
        name=result.name,
        vision=result.vision,
        goals=[
            TactGoal(id=g.id, description=g.description, success_criteria=g.success_criteria)
            for g in result.goals
        ],
        tech_stack=TactTechStack(
            languages=result.tech_stack.languages,
            frameworks=result.tech_stack.frameworks,
            infrastructure=result.tech_stack.infrastructure,
        ),
        constraints=result.constraints,
    )

    architecture = TactArchitecture(
        patterns=[
            TactArchitecturalPattern(name=p.name, description=p.description, scope=p.scope)
            for p in result.patterns
        ],
        invariants=result.invariants,
        conventions=result.conventions,
        decisions=[
            TactArchitecturalDecision(
                id=d.id, title=d.title, decision=d.decision, rationale=d.rationale
            )
            for d in result.decisions
        ],
    )

    valid_priorities = {"critical", "high", "medium", "low"}
    requirements = [
        TactRequirement(
            title=r.title,
            priority=r.priority if r.priority in valid_priorities else "medium",
            description=r.description,
            acceptance_criteria=r.acceptance_criteria if r.acceptance_criteria else ["TBD"],
            dependencies=r.dependencies,
        )
        for r in result.requirements
    ]

    return TactSpec(
        buildable_unit_id=unit.id,
        product=product,
        architecture=architecture,
        requirements=requirements,
    )
