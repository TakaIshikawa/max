"""Summarize source type and adapter category mix for profiles."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from max.profiles import loader as profile_loader
from max.profiles.schema import PipelineProfile, SourceConfig
from max.sources.registry import AdapterMetadata, get_adapter, get_adapter_metadata

DEFAULT_CONCENTRATION_THRESHOLD = 0.5

_LIMIT_PARAM_KEYS = (
    "limit",
    "max_items",
    "max_results",
    "max_rows",
    "max_pages",
    "per_page",
    "limit_per_query",
)

_CATEGORY_BY_ADAPTER: dict[str, str] = {
    "hackernews": "forum",
    "reddit": "forum",
    "stackoverflow": "forum",
    "stackexchange": "forum",
    "discourse": "forum",
    "lobsters": "forum",
    "devto": "forum",
    "bluesky": "social",
    "mastodon": "social",
    "npm_registry": "registry",
    "pypi_registry": "registry",
    "nuget": "registry",
    "maven_central": "registry",
    "rubygems": "registry",
    "packagist": "registry",
    "crates_io": "registry",
    "dockerhub": "registry",
    "homebrew_formulae": "registry",
    "terraform_registry": "registry",
    "go_packages": "registry",
    "mcp_registry": "registry",
    "github": "code_hosting",
    "github_issues": "code_hosting",
    "github_discussions": "code_hosting",
    "github_pull_requests": "code_hosting",
    "github_releases": "code_hosting",
    "gitlab_issues": "code_hosting",
    "gitlab_merge_requests": "code_hosting",
    "gitlab_releases": "code_hosting",
    "bitbucket_pull_requests": "code_hosting",
    "security_advisories": "security_feed",
    "osv_vulnerabilities": "security_feed",
    "cisa_kev": "security_feed",
    "nvd_cve": "security_feed",
    "openssf_scorecard": "security_feed",
    "openssf_security_insights": "security_feed",
    "snyk_reports": "security_feed",
    "agentseal_mcp_scan": "security_feed",
    "product_hunt": "marketplace",
    "github_marketplace_actions": "marketplace",
    "chrome_web_store": "marketplace",
    "open_vsx": "marketplace",
    "vscode_marketplace": "marketplace",
    "figma_community": "marketplace",
    "arxiv": "research",
    "openalex": "research",
    "pubmed": "research",
    "clinical_trials": "research",
    "stackoverflow_survey": "survey",
    "jetbrains_survey": "survey",
    "funding_rounds": "funding",
    "rss_feed": "article_feed",
}


@dataclass(frozen=True)
class ProfileSourceMixGroup:
    """One source mix group within a profile."""

    group: str
    source_type: str
    category: str
    adapter_count: int
    adapter_percentage: float
    total_weight: float
    weight_percentage: float
    total_configured_limit: int
    configured_limit_percentage: float
    adapters: list[str] = field(default_factory=list)
    over_concentrated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "group": self.group,
            "source_type": self.source_type,
            "category": self.category,
            "adapter_count": self.adapter_count,
            "adapter_percentage": self.adapter_percentage,
            "total_weight": self.total_weight,
            "weight_percentage": self.weight_percentage,
            "total_configured_limit": self.total_configured_limit,
            "configured_limit_percentage": self.configured_limit_percentage,
            "adapters": self.adapters,
            "over_concentrated": self.over_concentrated,
        }


@dataclass(frozen=True)
class ProfileSourceMixConcentrationFlag:
    """A group concentration finding for one metric."""

    group: str
    source_type: str
    category: str
    metric: str
    percentage: float
    threshold: float
    adapters: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "group": self.group,
            "source_type": self.source_type,
            "category": self.category,
            "metric": self.metric,
            "percentage": self.percentage,
            "threshold": self.threshold,
            "adapters": self.adapters,
        }


@dataclass(frozen=True)
class ProfileSourceMixRecommendation:
    """A source group that is available in the registry but absent from the profile."""

    group: str
    source_type: str
    category: str
    available_adapters: list[str] = field(default_factory=list)
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "group": self.group,
            "source_type": self.source_type,
            "category": self.category,
            "available_adapters": self.available_adapters,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ProfileSourceMixReport:
    """Profile-level source mix summary."""

    generated_at: str
    profile_name: str
    domain: str
    concentration_threshold: float
    enabled_adapter_count: int
    disabled_adapter_count: int
    total_weight: float
    total_configured_limit: int
    groups: list[ProfileSourceMixGroup] = field(default_factory=list)
    concentration_flags: list[ProfileSourceMixConcentrationFlag] = field(default_factory=list)
    recommendations: list[ProfileSourceMixRecommendation] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "profile_name": self.profile_name,
            "domain": self.domain,
            "concentration_threshold": self.concentration_threshold,
            "enabled_adapter_count": self.enabled_adapter_count,
            "disabled_adapter_count": self.disabled_adapter_count,
            "total_weight": self.total_weight,
            "total_configured_limit": self.total_configured_limit,
            "groups": [group.to_dict() for group in self.groups],
            "concentration_flags": [flag.to_dict() for flag in self.concentration_flags],
            "recommendations": [rec.to_dict() for rec in self.recommendations],
        }


def build_profile_source_mix(
    profile_name: str,
    *,
    concentration_threshold: float = DEFAULT_CONCENTRATION_THRESHOLD,
    now: datetime | None = None,
) -> ProfileSourceMixReport:
    """Load a profile and summarize its enabled source mix."""
    profile = profile_loader.load_profile(profile_name)
    return build_profile_source_mix_for_profile(
        profile,
        concentration_threshold=concentration_threshold,
        now=now,
    )


def build_profile_source_mix_for_profile(
    profile: PipelineProfile,
    *,
    concentration_threshold: float = DEFAULT_CONCENTRATION_THRESHOLD,
    now: datetime | None = None,
) -> ProfileSourceMixReport:
    """Summarize an already loaded profile's source mix."""
    if concentration_threshold <= 0 or concentration_threshold > 1:
        raise ValueError("concentration_threshold must be greater than 0 and at most 1")

    metadata = get_adapter_metadata()
    generated_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
    enabled_sources = [source for source in profile.sources if source.enabled]
    disabled_sources = [source for source in profile.sources if not source.enabled]
    total_weight = round(sum(float(source.weight) for source in enabled_sources), 4)
    total_configured_limit = sum(_configured_limit(source) for source in enabled_sources)
    groups_by_key: dict[tuple[str, str], list[SourceConfig]] = defaultdict(list)

    for source in enabled_sources:
        source_type = _adapter_source_type(source.adapter)
        category = _adapter_category(source.adapter, metadata.get(source.adapter), source_type)
        groups_by_key[(source_type, category)].append(source)

    groups = [
        _build_group(
            source_type=source_type,
            category=category,
            sources=sources,
            enabled_adapter_count=len(enabled_sources),
            total_weight=total_weight,
            total_configured_limit=total_configured_limit,
            concentration_threshold=concentration_threshold,
        )
        for (source_type, category), sources in groups_by_key.items()
    ]
    groups.sort(key=lambda group: (group.source_type, group.category))

    concentration_flags = _concentration_flags(groups, concentration_threshold)
    enabled_group_keys = {(group.source_type, group.category) for group in groups}
    recommendations = _underrepresented_recommendations(
        metadata,
        enabled_adapters={source.adapter for source in enabled_sources},
        enabled_group_keys=enabled_group_keys,
    )

    return ProfileSourceMixReport(
        generated_at=generated_at,
        profile_name=profile.name,
        domain=profile.domain.name,
        concentration_threshold=concentration_threshold,
        enabled_adapter_count=len(enabled_sources),
        disabled_adapter_count=len(disabled_sources),
        total_weight=total_weight,
        total_configured_limit=total_configured_limit,
        groups=groups,
        concentration_flags=concentration_flags,
        recommendations=recommendations,
    )


def _build_group(
    *,
    source_type: str,
    category: str,
    sources: list[SourceConfig],
    enabled_adapter_count: int,
    total_weight: float,
    total_configured_limit: int,
    concentration_threshold: float,
) -> ProfileSourceMixGroup:
    adapters = sorted(source.adapter for source in sources)
    group_weight = round(sum(float(source.weight) for source in sources), 4)
    group_limit = sum(_configured_limit(source) for source in sources)
    adapter_percentage = _percentage(len(sources), enabled_adapter_count)
    weight_percentage = _percentage(group_weight, total_weight)
    limit_percentage = _percentage(group_limit, total_configured_limit)
    over_concentrated = any(
        percentage > concentration_threshold
        for percentage in (adapter_percentage, weight_percentage, limit_percentage)
        if percentage > 0
    )
    return ProfileSourceMixGroup(
        group=_group_name(source_type, category),
        source_type=source_type,
        category=category,
        adapter_count=len(sources),
        adapter_percentage=adapter_percentage,
        total_weight=group_weight,
        weight_percentage=weight_percentage,
        total_configured_limit=group_limit,
        configured_limit_percentage=limit_percentage,
        adapters=adapters,
        over_concentrated=over_concentrated,
    )


def _concentration_flags(
    groups: list[ProfileSourceMixGroup],
    concentration_threshold: float,
) -> list[ProfileSourceMixConcentrationFlag]:
    flags: list[ProfileSourceMixConcentrationFlag] = []
    for group in groups:
        for metric, percentage in (
            ("adapter_count", group.adapter_percentage),
            ("weight", group.weight_percentage),
            ("configured_limit", group.configured_limit_percentage),
        ):
            if percentage > concentration_threshold:
                flags.append(
                    ProfileSourceMixConcentrationFlag(
                        group=group.group,
                        source_type=group.source_type,
                        category=group.category,
                        metric=metric,
                        percentage=percentage,
                        threshold=concentration_threshold,
                        adapters=group.adapters,
                    )
                )
    return sorted(flags, key=lambda flag: (-flag.percentage, flag.group, flag.metric))


def _underrepresented_recommendations(
    metadata: dict[str, AdapterMetadata],
    *,
    enabled_adapters: set[str],
    enabled_group_keys: set[tuple[str, str]],
) -> list[ProfileSourceMixRecommendation]:
    adapters_by_group: dict[tuple[str, str], list[str]] = defaultdict(list)
    for adapter, adapter_metadata in metadata.items():
        source_type = _adapter_source_type(adapter)
        category = _adapter_category(adapter, adapter_metadata, source_type)
        adapters_by_group[(source_type, category)].append(adapter)

    recommendations: list[ProfileSourceMixRecommendation] = []
    for (source_type, category), adapters in adapters_by_group.items():
        if (source_type, category) in enabled_group_keys:
            continue
        available = sorted(adapter for adapter in adapters if adapter not in enabled_adapters)
        if not available:
            continue
        recommendations.append(
            ProfileSourceMixRecommendation(
                group=_group_name(source_type, category),
                source_type=source_type,
                category=category,
                available_adapters=available[:5],
                reason=(
                    f"No enabled {source_type}/{category} sources are configured; "
                    "registry metadata includes adapters for this group."
                ),
            )
        )
    return sorted(recommendations, key=lambda rec: (rec.source_type, rec.category))


def _adapter_source_type(adapter: str) -> str:
    try:
        source_type = get_adapter(adapter).source_type
    except Exception:
        return "unknown"
    if hasattr(source_type, "value"):
        return str(source_type.value)
    return str(source_type)


def _adapter_category(
    adapter: str,
    metadata: AdapterMetadata | None,
    source_type: str,
) -> str:
    if adapter in _CATEGORY_BY_ADAPTER:
        return _CATEGORY_BY_ADAPTER[adapter]

    searchable = f"{adapter} {metadata.description if metadata else ''}".lower()
    if any(term in searchable for term in ("security", "vulnerab", "cve", "advisor")):
        return "security_feed"
    if any(term in searchable for term in ("registry", "package", "crates", "maven", "nuget")):
        return "registry"
    if any(term in searchable for term in ("forum", "discussion", "issue", "pull request")):
        return "forum"
    if any(term in searchable for term in ("marketplace", "store", "product")):
        return "marketplace"
    if any(term in searchable for term in ("survey", "research", "paper", "clinical")):
        return "research"
    return source_type or "unknown"


def _configured_limit(source: SourceConfig) -> int:
    values: list[int] = []
    for key in _LIMIT_PARAM_KEYS:
        value = source.params.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            values.append(value)
        elif isinstance(value, float) and value.is_integer():
            values.append(int(value))
    return max(values, default=0)


def _percentage(value: float | int, total: float | int) -> float:
    if not total:
        return 0.0
    return round(float(value) / float(total), 4)


def _group_name(source_type: str, category: str) -> str:
    return f"{source_type}/{category}"
