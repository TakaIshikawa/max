"""TactSpec — tact-compatible project specification bundle."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class TactGoal(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    description: str
    success_criteria: str = Field(alias="successCriteria")


class TactTechStack(BaseModel):
    languages: list[str] = Field(default_factory=list)
    frameworks: list[str] = Field(default_factory=list)
    infrastructure: list[str] = Field(default_factory=list)


class TactProduct(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    version: str = "0.1.0"
    vision: str
    goals: list[TactGoal] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    tech_stack: TactTechStack = Field(
        default_factory=TactTechStack,
        alias="techStack",
    )


class TactArchitecturalPattern(BaseModel):
    name: str
    description: str
    scope: list[str] = Field(default_factory=list)


class TactArchitecturalDecision(BaseModel):
    id: str
    title: str
    decision: str
    rationale: str


class TactSharedContract(BaseModel):
    id: str
    name: str
    type: str  # type_definition | api_contract | config_file | dependency | schema
    files: list[str] = Field(default_factory=list)
    description: str


class TactArchitecture(BaseModel):
    patterns: list[TactArchitecturalPattern] = Field(default_factory=list)
    invariants: list[str] = Field(default_factory=list)
    conventions: list[str] = Field(default_factory=list)
    decisions: list[TactArchitecturalDecision] = Field(default_factory=list)
    contracts: list[TactSharedContract] = Field(default_factory=list)


class TactRequirement(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    title: str
    approval: str = "draft"
    phase: str = "planned"
    priority: str = "medium"  # critical | high | medium | low
    description: str = ""
    acceptance_criteria: list[str] = Field(
        default_factory=list,
        alias="acceptanceCriteria",
        min_length=1,
    )
    decomposition: dict = Field(default_factory=lambda: {"assignments": []})
    dependencies: list[str] = Field(default_factory=list)
    source: str = "discovered"


class TactSpec(BaseModel):
    """Complete spec bundle for a single project."""

    buildable_unit_id: str
    product: TactProduct
    architecture: TactArchitecture
    requirements: list[TactRequirement]
