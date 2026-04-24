"""Pipeline profile schema — Pydantic models for YAML-based pipeline configuration."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field, model_validator

_WATCHLIST_PARAM_KEYS = {
    "arxiv": "queries",
    "bluesky": "queries",
    "devto": "tags",
    "github": "topics",
    "github_discussions": "search_terms",
    "github_issues": "queries",
    "gitlab_releases": "query_terms",
    "hackernews": "filter_keywords",
    "huggingface": "queries",
    "nuget": "queries",
    "npm_registry": "queries",
    "nvd_cve": "keywords",
    "product_hunt": "topics",
    "pubmed": "queries",
    "pypi_registry": "keywords",
    "reddit": "subreddits",
    "stackoverflow": "tags",
}


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _validate_string_list(value: Any, field_name: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list of strings")
    terms: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field_name} must be a list of non-empty strings")
        terms.append(item.strip())
    return terms


class SourceConfig(BaseModel):
    """Per-adapter configuration within a profile."""

    adapter: str  # adapter name (e.g. "reddit", "github")
    enabled: bool = True
    weight: float = 1.0  # relative fetch budget weight
    watchlist: list[str] = Field(default_factory=list)
    params: dict[str, Any] = Field(default_factory=dict)
    # params vary by adapter:
    #   reddit: {"subreddits": [...]}
    #   github: {"topics": [...]}
    #   github_issues: {"queries": [...]}
    #   nuget: {"queries": [...], "package_names": [...]}
    #   npm_registry: {"queries": [...]}
    #   pypi_registry: {"keywords": [...]}
    #   security_advisories: {"ecosystems": [...], "severities": [...]}
    #   nvd_cve: {"keywords": [...], "severities": [...], "cvss_min": 7.0}
    #   product_hunt: {"topics": [...]}
    #   hackernews: {"filter_keywords": [...]}
    #   rss_feed: {"feeds": ["https://example.com/feed.xml"], "max_age_days": 14}

    @model_validator(mode="after")
    def validate_adapter_params(self) -> "SourceConfig":
        self.watchlist = _validate_string_list(self.watchlist, "watchlist")

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

    @property
    def normalized_params(self) -> dict[str, Any]:
        """Adapter params with watchlist terms normalized into query/filter keys."""
        params = dict(self.params)
        watchlist_terms = _dedupe_strings(self.watchlist)
        if not watchlist_terms:
            return params

        params["watchlist_terms"] = watchlist_terms

        param_key = _WATCHLIST_PARAM_KEYS.get(self.adapter)
        if param_key is None:
            return params

        existing = params.get(param_key)
        if existing is None:
            existing_terms: list[str] = []
        else:
            existing_terms = _validate_string_list(
                existing,
                f"params.{param_key}",
            )
        params[param_key] = _dedupe_strings(existing_terms + watchlist_terms)
        return params


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


class ArchitectureConstraintsConfig(BaseModel):
    """Optional architecture expectations enforced against generated ideas."""

    allowed_categories: list[str] = Field(default_factory=list)
    allowed_target_users: list[str] = Field(default_factory=list)
    allowed_domains: list[str] = Field(default_factory=list)
    required_stack_decisions: list[str] = Field(default_factory=list)
    allowed_stack_items: dict[str, list[str]] = Field(default_factory=dict)
    rejected_stack_items: dict[str, list[str]] = Field(default_factory=dict)
    allowed_deployment_patterns: list[str] = Field(default_factory=list)
    rejected_deployment_patterns: list[str] = Field(default_factory=list)
    required_integrations: list[str] = Field(default_factory=list)
    allowed_integrations: list[str] = Field(default_factory=list)
    rejected_integrations: list[str] = Field(default_factory=list)
    required_tech_approach_terms: list[str] = Field(default_factory=list)
    rejected_tech_approach_terms: list[str] = Field(default_factory=list)
    notes: str = ""


class PipelineProfile(BaseModel):
    """Complete pipeline profile loaded from YAML."""

    name: str
    domain: DomainContext
    domain_quality: DomainQualityConfig = Field(default_factory=DomainQualityConfig)
    architecture_constraints: ArchitectureConstraintsConfig = Field(
        default_factory=ArchitectureConstraintsConfig
    )
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
