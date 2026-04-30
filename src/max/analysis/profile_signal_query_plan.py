"""Deterministic source query plans for loaded pipeline profiles."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from max.profiles.loader import load_profile
from max.profiles.schema import PipelineProfile, SourceConfig

SCHEMA_VERSION = "max.profile.signal_query_plan.v1"

_QUERY_PARAM_KEYS = (
    "queries",
    "query_terms",
    "search_terms",
    "keywords",
    "filter_keywords",
    "topics",
    "tags",
    "subreddits",
    "categories",
    "category_slugs",
    "ecosystems",
    "severities",
    "package_names",
    "repositories",
    "projects",
    "feeds",
    "workflow_names",
    "workflows",
    "watchlist_terms",
)

_FRESHNESS_WINDOWS_BY_ADAPTER = {
    "arxiv": "90 days",
    "github": "30 days",
    "github_discussions": "30 days",
    "github_issues": "30 days",
    "github_pull_requests": "14 days",
    "github_releases": "30 days",
    "hackernews": "14 days",
    "nuget": "30 days",
    "npm_registry": "30 days",
    "product_hunt": "30 days",
    "pypi_registry": "30 days",
    "reddit": "14 days",
    "rss_feed": "14 days",
    "security_advisories": "14 days",
    "stackoverflow": "30 days",
}

_ROLE_HINTS_BY_ADAPTER = {
    "arxiv": ["technical novelty", "research trend"],
    "devto": ["workflow pain", "implementation pattern"],
    "github": ["solution momentum", "implementation pattern"],
    "github_discussions": ["workflow pain", "adoption friction"],
    "github_issues": ["problem evidence", "adoption friction"],
    "hackernews": ["market pull", "developer pain"],
    "nuget": ["ecosystem adoption", "implementation pattern"],
    "npm_registry": ["ecosystem adoption", "implementation pattern"],
    "product_hunt": ["market pull", "competitor signal"],
    "pypi_registry": ["ecosystem adoption", "implementation pattern"],
    "reddit": ["workflow pain", "market pull"],
    "security_advisories": ["risk signal", "trust constraint"],
    "stackoverflow": ["developer pain", "implementation friction"],
}

_REQUIRED_PROFILE_FIELDS: tuple[tuple[str, str], ...] = (
    ("domain.description", "Domain description is needed to ground broad source queries."),
    ("domain.categories", "Domain categories are needed to cover buildable opportunity types."),
    (
        "domain.target_user_types",
        "Target user types are needed to include user language in suggested queries.",
    ),
    ("sources", "At least one enabled source is needed before adapter execution."),
)


def build_profile_signal_query_plan(profile: PipelineProfile) -> dict[str, Any]:
    """Build a JSON-ready source query plan from a loaded profile."""
    enabled_sources = [source for source in profile.sources if source.enabled]
    disabled_sources = [source for source in profile.sources if not source.enabled]
    source_entries = [_source_entry(profile, source) for source in enabled_sources]
    gaps = _profile_gaps(profile, enabled_sources, source_entries)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "max.profile.signal_query_plan",
        "profile": {
            "name": profile.name,
            "domain": profile.domain.name,
            "description": _clean(profile.domain.description),
            "signal_limit": profile.signal_limit,
            "ideation_mode": profile.ideation_mode,
        },
        "summary": {
            "enabled_source_count": len(enabled_sources),
            "disabled_source_count": len(disabled_sources),
            "source_entry_count": len(source_entries),
            "suggested_query_count": sum(
                len(source["suggested_queries"]) for source in source_entries
            ),
            "gap_count": len(gaps),
        },
        "domain_terms": _domain_terms(profile),
        "category_terms": _string_list(profile.domain.categories),
        "target_user_terms": _target_user_terms(profile),
        "sources": source_entries,
        "gaps": gaps,
    }


def build_profile_signal_query_plan_by_name(profile_name: str) -> dict[str, Any]:
    """Load a profile by name and build its source query plan."""
    return build_profile_signal_query_plan(load_profile(profile_name))


def render_profile_signal_query_plan(plan: dict[str, Any], *, fmt: str = "markdown") -> str:
    """Render a profile signal query plan as Markdown or JSON."""
    if fmt == "json":
        return json.dumps(plan, indent=2, sort_keys=True) + "\n"
    if fmt != "markdown":
        raise ValueError(f"Unsupported profile signal query plan format: {fmt}")

    profile = plan["profile"]
    lines = [
        f"# Profile Signal Query Plan: {profile['name']}",
        "",
        f"Schema: `{plan['schema_version']}`",
        f"Domain: `{profile['domain']}`",
        "",
        "## Source Queries",
        "",
        "| Source | Query Terms | Suggested Queries | Freshness Window | Expected Signal Roles |",
        "| --- | --- | --- | --- | --- |",
    ]
    for source in plan["sources"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{source['adapter']}`",
                    _inline_code(source["query_terms"]),
                    _escape_table("; ".join(source["suggested_queries"]) or "None"),
                    source["freshness_window"],
                    _inline_code(source["expected_signal_roles"]),
                ]
            )
            + " |"
        )

    lines.extend(["", "## Domain Terms", ""])
    lines.append(f"- Domain: {_inline_code(plan['domain_terms'])}")
    lines.append(f"- Categories: {_inline_code(plan['category_terms'])}")
    lines.append(f"- Target users: {_inline_code(plan['target_user_terms'])}")

    lines.extend(["", "## Gaps", ""])
    if plan["gaps"]:
        lines.extend(
            f"- **{gap['field']}** (`{gap['severity']}`): {gap['reason']}"
            for gap in plan["gaps"]
        )
    else:
        lines.append("- None")

    return "\n".join(lines).rstrip() + "\n"


def write_profile_signal_query_plan(
    path: Path,
    plan: dict[str, Any],
    *,
    fmt: str = "markdown",
) -> None:
    """Write a rendered profile signal query plan to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_profile_signal_query_plan(plan, fmt=fmt), encoding="utf-8")


def profile_signal_query_plan_filename(
    profile: PipelineProfile | dict[str, Any],
    *,
    fmt: str = "markdown",
) -> str:
    """Return a stable filename for a profile signal query plan."""
    extension = "json" if fmt == "json" else "md"
    if isinstance(profile, PipelineProfile):
        name = profile.name
    else:
        name = _clean(profile.get("name")) or "profile"
    return f"{_filename_part(name)}-signal-query-plan.{extension}"


def _source_entry(profile: PipelineProfile, source: SourceConfig) -> dict[str, Any]:
    query_terms = _source_query_terms(source)
    suggested_queries = _suggested_queries(profile, source, query_terms)
    freshness_window = _freshness_window(source)

    return {
        "adapter": source.adapter,
        "enabled": source.enabled,
        "weight": source.weight,
        "query_terms": query_terms,
        "suggested_queries": suggested_queries,
        "freshness_window": freshness_window,
        "expected_signal_roles": _expected_signal_roles(source),
        "params": _json_ready(source.normalized_params),
    }


def _suggested_queries(
    profile: PipelineProfile,
    source: SourceConfig,
    query_terms: list[str],
) -> list[str]:
    domain_terms = _domain_terms(profile)
    categories = _string_list(profile.domain.categories)
    users = _target_user_terms(profile)
    workflows = _string_list(profile.domain.workflows)
    base_terms = _dedupe([*query_terms[:4], *domain_terms[:2], *categories[:2], *users[:2]])
    queries: list[str] = []

    if base_terms and (query_terms or categories or users or workflows):
        queries.append(" ".join(base_terms[:6]))
    if categories and users:
        queries.append(f"{profile.domain.name} {categories[0]} for {users[0]}")
    if query_terms and workflows:
        queries.append(f"{query_terms[0]} {workflows[0]}")
    if not queries:
        queries.append(f"{profile.domain.name} signal discovery")

    if source.adapter in {"github_issues", "github_discussions"}:
        queries.append(f'"{profile.domain.name}" is:open')
    elif source.adapter == "stackoverflow" and query_terms:
        queries.append(" ".join(f"[{term}]" for term in query_terms[:3]))
    elif source.adapter in {"npm_registry", "pypi_registry", "nuget"} and categories:
        queries.append(f"{categories[0]} package")
    elif source.adapter in {"security_advisories", "nvd_cve", "cisa_kev"}:
        queries.append(f"{profile.domain.name} vulnerability advisory")

    return _dedupe(queries)[:4]


def _source_query_terms(source: SourceConfig) -> list[str]:
    params = source.normalized_params
    terms: list[str] = []
    for key in _QUERY_PARAM_KEYS:
        terms.extend(_string_list(params.get(key)))
    terms.extend(_string_list(source.watchlist))
    return _dedupe(terms)


def _freshness_window(source: SourceConfig) -> str:
    params = source.normalized_params
    max_age_days = params.get("max_age_days") or params.get("recent_days")
    if isinstance(max_age_days, int) and not isinstance(max_age_days, bool) and max_age_days > 0:
        return f"{max_age_days} days"
    return _FRESHNESS_WINDOWS_BY_ADAPTER.get(source.adapter, "30 days")


def _expected_signal_roles(source: SourceConfig) -> list[str]:
    return _ROLE_HINTS_BY_ADAPTER.get(source.adapter, ["problem evidence", "market signal"])


def _profile_gaps(
    profile: PipelineProfile,
    enabled_sources: list[SourceConfig],
    source_entries: list[dict[str, Any]],
) -> list[dict[str, str]]:
    gaps: list[dict[str, str]] = []
    values_by_field = {
        "domain.description": _clean(profile.domain.description),
        "domain.categories": _string_list(profile.domain.categories),
        "domain.target_user_types": _string_list(profile.domain.target_user_types),
        "sources": enabled_sources,
    }
    for field, reason in _REQUIRED_PROFILE_FIELDS:
        if not values_by_field[field]:
            gaps.append({"field": field, "severity": "missing", "reason": reason})

    if len(_clean(profile.domain.description)) < 30:
        gaps.append(
            {
                "field": "domain.description",
                "severity": "weak",
                "reason": "Domain description is short; suggested queries may be too generic.",
            }
        )
    if len(_string_list(profile.domain.categories)) < 2:
        gaps.append(
            {
                "field": "domain.categories",
                "severity": "weak",
                "reason": "Fewer than two categories limits query diversity across opportunity types.",
            }
        )
    if len(_target_user_terms(profile)) < 2:
        gaps.append(
            {
                "field": "domain.target_user_types",
                "severity": "weak",
                "reason": "Only one target user term is available for user-language query expansion.",
            }
        )

    for source in source_entries:
        if not source["query_terms"]:
            gaps.append(
                {
                    "field": f"sources.{source['adapter']}.params",
                    "severity": "weak",
                    "reason": "Enabled source has no query-like params or watchlist terms.",
                }
            )
    return gaps


def _domain_terms(profile: PipelineProfile) -> list[str]:
    return _dedupe(
        [
            profile.domain.name,
            *_string_list(profile.domain.target_segments),
            *_string_list(profile.domain.workflows),
            *_string_list(profile.domain.buyer_roles),
        ]
    )


def _target_user_terms(profile: PipelineProfile) -> list[str]:
    return _dedupe(
        [
            *_string_list(profile.domain.target_user_types),
            *_string_list(profile.domain.target_segments),
            *_string_list(profile.domain.buyer_roles),
        ]
    )


def _json_ready(value: Any) -> Any:
    return json.loads(json.dumps(value, sort_keys=True, default=str))


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        cleaned = _clean(value)
        return [cleaned] if cleaned else []
    if isinstance(value, dict):
        return [_clean(key) for key in value if _clean(key)]
    if isinstance(value, list | tuple | set):
        return [_clean(item) for item in value if _clean(item)]
    return [_clean(value)] if _clean(value) else []


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        key = value.casefold()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(value)
    return deduped


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _inline_code(values: list[str]) -> str:
    return ", ".join(f"`{value}`" for value in values) if values else "None"


def _escape_table(value: str) -> str:
    return value.replace("|", "\\|")


def _filename_part(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in value)
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-_")
