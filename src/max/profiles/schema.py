"""Pipeline profile schema — Pydantic models for YAML-based pipeline configuration."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SourceConfig(BaseModel):
    """Per-adapter configuration within a profile."""

    adapter: str  # adapter name (e.g. "reddit", "github")
    enabled: bool = True
    weight: float = 1.0  # relative fetch budget weight
    params: dict = Field(default_factory=dict)
    # params vary by adapter:
    #   reddit: {"subreddits": [...]}
    #   github: {"topics": [...]}
    #   github_issues: {"queries": [...]}
    #   npm_registry: {"queries": [...]}
    #   pypi_registry: {"keywords": [...]}
    #   security_advisories: {"ecosystems": [...], "severities": [...]}
    #   product_hunt: {"topics": [...]}
    #   hackernews: {"filter_keywords": [...]}


class DomainContext(BaseModel):
    """Domain description injected into LLM prompts."""

    name: str  # e.g. "healthcare", "developer-tools"
    description: str  # 1-2 sentence domain description for LLM system prompts
    categories: list[str]  # valid buildable categories for this domain
    target_user_types: list[str]  # e.g. ["clinicians", "patients", "both"]
    extra_instructions: str = ""  # optional domain-specific prompt additions


class EvaluationConfig(BaseModel):
    """Evaluation parameters from profile."""

    weight_profile: str = "default"
    custom_weights: dict[str, float] | None = None
    min_score: float = 50.0


class PipelineProfile(BaseModel):
    """Complete pipeline profile loaded from YAML."""

    name: str
    domain: DomainContext
    sources: list[SourceConfig] = Field(default_factory=list)
    evaluation: EvaluationConfig = Field(default_factory=EvaluationConfig)
    output_dir: str = ".tact"
    signal_limit: int = 30
    ideation_mode: str = "direct"


# Default domain context — captures current dev-tools behavior
DEFAULT_DOMAIN_CONTEXT = DomainContext(
    name="developer-tools",
    description=(
        "developer tools and AI agent ecosystem. "
        "Focus on tools for software engineers, AI agents, and the infrastructure connecting them"
    ),
    categories=[
        "mcp_server",
        "cli_tool",
        "library",
        "integration",
        "automation",
        "application",
        "feature",
    ],
    target_user_types=["humans", "agents", "both"],
)
