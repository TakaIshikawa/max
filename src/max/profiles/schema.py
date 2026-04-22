"""Pipeline profile schema — Pydantic models for YAML-based pipeline configuration."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field, model_validator


class SourceConfig(BaseModel):
    """Per-adapter configuration within a profile."""

    adapter: str  # adapter name (e.g. "reddit", "github")
    enabled: bool = True
    weight: float = 1.0  # relative fetch budget weight
    params: dict[str, Any] = Field(default_factory=dict)
    # params vary by adapter:
    #   reddit: {"subreddits": [...]}
    #   github: {"topics": [...]}
    #   github_issues: {"queries": [...]}
    #   npm_registry: {"queries": [...]}
    #   pypi_registry: {"keywords": [...]}
    #   security_advisories: {"ecosystems": [...], "severities": [...]}
    #   nvd_cve: {"keywords": [...], "severities": [...], "cvss_min": 7.0}
    #   product_hunt: {"topics": [...]}
    #   hackernews: {"filter_keywords": [...]}
    #   rss_feed: {"feeds": ["https://example.com/feed.xml"], "max_age_days": 14}

    @model_validator(mode="after")
    def validate_adapter_params(self) -> "SourceConfig":
        if self.adapter != "rss_feed":
            return self

        feeds = self.params.get("feeds")
        if feeds is not None:
            if not isinstance(feeds, list):
                raise ValueError("rss_feed params.feeds must be a list of URL strings")
            for feed_url in feeds:
                if not isinstance(feed_url, str) or not feed_url.strip():
                    raise ValueError("rss_feed params.feeds must be a list of URL strings")
                parsed = urlparse(feed_url)
                if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                    raise ValueError("rss_feed params.feeds must contain HTTP(S) URL strings")

        max_age_days = self.params.get("max_age_days")
        if max_age_days is not None:
            if not isinstance(max_age_days, int) or isinstance(max_age_days, bool):
                raise ValueError("rss_feed params.max_age_days must be an integer")
            if max_age_days < 1:
                raise ValueError("rss_feed params.max_age_days must be at least 1")

        return self


class DomainContext(BaseModel):
    """Domain description injected into LLM prompts."""

    name: str  # e.g. "healthcare", "developer-tools"
    description: str  # 1-2 sentence domain description for LLM system prompts
    categories: list[str]  # valid buildable categories for this domain
    target_user_types: list[str]  # e.g. ["clinicians", "patients", "both"]
    extra_instructions: str = ""  # optional domain-specific prompt additions
    target_segments: list[str] = Field(default_factory=list)
    workflows: list[str] = Field(default_factory=list)
    buyer_roles: list[str] = Field(default_factory=list)
    hard_constraints: list[str] = Field(default_factory=list)
    bad_idea_patterns: list[str] = Field(default_factory=list)
    good_idea_criteria: list[str] = Field(default_factory=list)


class DomainQualityDimension(BaseModel):
    """A domain-local quality dimension and its relative weight."""

    weight: float = 1.0
    description: str = ""


class DomainQualityConfig(BaseModel):
    """Domain-specific idea scoring and enforcement rules."""

    enabled: bool = False
    min_score: float = 65.0
    required_fields: list[str] = Field(default_factory=list)
    scoring_dimensions: dict[str, DomainQualityDimension] = Field(default_factory=dict)
    hard_rejections: list[str] = Field(default_factory=list)
    preferred_patterns: list[str] = Field(default_factory=list)
    rejected_patterns: list[str] = Field(default_factory=list)
    rubric_version: str = "v1"


class EvaluationConfig(BaseModel):
    """Evaluation parameters from profile."""

    weight_profile: str = "default"
    custom_weights: dict[str, float] | None = None
    min_score: float = 50.0


class PipelineProfile(BaseModel):
    """Complete pipeline profile loaded from YAML."""

    name: str
    domain: DomainContext
    domain_quality: DomainQualityConfig = Field(default_factory=DomainQualityConfig)
    sources: list[SourceConfig] = Field(default_factory=list)
    evaluation: EvaluationConfig = Field(default_factory=EvaluationConfig)
    output_dir: str = ".max-output"
    signal_limit: int = 30
    ideation_mode: str = "direct"
    quality_loop_enabled: bool = False
    draft_count: int = 8


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
