"""BuildableUnit — an idea for something to build."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field


class BuildableCategory(StrEnum):
    MCP_SERVER = "mcp_server"
    CLI_TOOL = "cli_tool"
    LIBRARY = "library"
    INTEGRATION = "integration"
    AUTOMATION = "automation"
    APPLICATION = "application"
    FEATURE = "feature"


class IdeationMode(StrEnum):
    DIRECT = "direct"
    REFINEMENT = "refinement"
    CROSS_DOMAIN = "cross_domain"
    SYNTHESIS = "synthesis"
    CROSS_SYNTHESIS = "cross_synthesis"


class BuildableUnit(BaseModel):
    id: str = Field(default="")
    title: str
    one_liner: str
    category: str  # Profile-defined categories (see BuildableCategory for well-known values)
    ideation_mode: IdeationMode = IdeationMode.DIRECT

    # Problem / Solution
    problem: str
    solution: str
    target_users: str = "both"  # humans | agents | both
    value_proposition: str

    # Traceability
    inspiring_insights: list[str] = Field(default_factory=list)  # Insight IDs
    evidence_signals: list[str] = Field(default_factory=list)  # Signal IDs (transitive)
    source_idea_ids: list[str] = Field(default_factory=list)  # BuildableUnit IDs merged into this

    # Technical sketch
    tech_approach: str = ""
    suggested_stack: dict = Field(default_factory=dict)
    composability_notes: str = ""

    # Domain (profile name that generated this unit)
    domain: str = ""

    # Prior art check status
    prior_art_status: str = "unchecked"  # unchecked | clear | weak_match | strong_match

    # Status
    status: str = "draft"  # draft | evaluated | approved | published | rejected
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
