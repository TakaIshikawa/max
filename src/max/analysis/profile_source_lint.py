"""Lint profile source configuration against adapter registry metadata."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import yaml

from max.profiles.loader import get_profile_path, list_profile_paths
from max.sources.registry import AdapterMetadata, get_adapter_metadata

LintSeverity = Literal["info", "warning", "error"]

_SEVERITY_ORDER: dict[LintSeverity, int] = {"error": 0, "warning": 1, "info": 2}

_COMMON_PARAM_TYPES: dict[str, type | tuple[type, ...]] = {
    "api_key_env": str,
    "base_url": str,
    "endpoint": str,
    "from_publication_date": str,
    "gitlab_base_url": str,
    "github_token": str,
    "include_answered": bool,
    "include_descriptions": bool,
    "include_drafts": bool,
    "include_prerelease": bool,
    "include_prereleases": bool,
    "include_tags": bool,
    "local_path": str,
    "max_age_days": int,
    "max_pages": int,
    "max_rows": int,
    "max_results_per_query": int,
    "min_comments": int,
    "min_percent": (int, float),
    "min_risk_score": (int, float),
    "min_score": (int, float),
    "min_stars": int,
    "min_upvotes": int,
    "page": int,
    "per_page": int,
    "period": str,
    "recent_days": int,
    "sort": str,
    "state": str,
    "status": str,
    "token": str,
    "token_env": str,
}

_LIST_PARAM_KEYS = {
    "base_urls",
    "categories",
    "category_slugs",
    "checks",
    "concepts",
    "conclusions",
    "domains",
    "ecosystems",
    "feeds",
    "filter_keywords",
    "keywords",
    "labels",
    "lists",
    "local_paths",
    "package_names",
    "project_ids",
    "projects",
    "queries",
    "query_terms",
    "question_filters",
    "repositories",
    "resource_types",
    "search_terms",
    "severities",
    "stacks",
    "statuses",
    "subreddits",
    "survey_urls",
    "tags",
    "topics",
    "workflow_names",
    "workflows",
}


@dataclass(frozen=True)
class ProfileSourceLintIssue:
    """One actionable source-configuration lint finding."""

    severity: LintSeverity
    code: str
    profile_name: str
    profile_path: str
    path: str
    adapter: str
    message: str
    suggested_fix: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "profile_name": self.profile_name,
            "profile_path": self.profile_path,
            "path": self.path,
            "adapter": self.adapter,
            "message": self.message,
            "suggested_fix": self.suggested_fix,
        }


@dataclass(frozen=True)
class ProfileSourceLintReport:
    """Lint report for a single profile."""

    generated_at: str
    profile_name: str
    profile_path: str
    ok: bool
    issue_counts_by_severity: dict[str, int] = field(default_factory=dict)
    issue_counts_by_adapter: dict[str, int] = field(default_factory=dict)
    issues: list[ProfileSourceLintIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "profile_name": self.profile_name,
            "profile_path": self.profile_path,
            "ok": self.ok,
            "issue_counts_by_severity": self.issue_counts_by_severity,
            "issue_counts_by_adapter": self.issue_counts_by_adapter,
            "issues": [issue.to_dict() for issue in self.issues],
        }


@dataclass(frozen=True)
class AllProfileSourceLintReport:
    """Lint report for all discovered profiles."""

    generated_at: str
    ok: bool
    profile_count: int
    issue_counts_by_severity: dict[str, int] = field(default_factory=dict)
    issue_counts_by_adapter: dict[str, int] = field(default_factory=dict)
    profiles: list[ProfileSourceLintReport] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "ok": self.ok,
            "profile_count": self.profile_count,
            "issue_counts_by_severity": self.issue_counts_by_severity,
            "issue_counts_by_adapter": self.issue_counts_by_adapter,
            "profiles": [profile.to_dict() for profile in self.profiles],
        }


def build_profile_source_lint_report(profile_name: str) -> ProfileSourceLintReport:
    """Build a lint report for one named profile."""
    profile_path = get_profile_path(profile_name)
    metadata = get_adapter_metadata()
    return _build_profile_source_lint_report_from_path(profile_path, metadata)


def build_all_profile_source_lint_report() -> AllProfileSourceLintReport:
    """Build lint reports for all discovered profiles."""
    generated_at = _generated_at()
    metadata = get_adapter_metadata()
    reports = [
        _build_profile_source_lint_report_from_path(path, metadata, generated_at=generated_at)
        for path in list_profile_paths()
    ]
    severity_counts = _sum_counts(report.issue_counts_by_severity for report in reports)
    adapter_counts = _sum_counts(report.issue_counts_by_adapter for report in reports)
    return AllProfileSourceLintReport(
        generated_at=generated_at,
        ok=all(report.ok for report in reports),
        profile_count=len(reports),
        issue_counts_by_severity=severity_counts,
        issue_counts_by_adapter=adapter_counts,
        profiles=reports,
    )


def _build_profile_source_lint_report_from_path(
    profile_path: Path,
    metadata: dict[str, AdapterMetadata],
    *,
    generated_at: str | None = None,
) -> ProfileSourceLintReport:
    generated_at = generated_at or _generated_at()
    profile_name = profile_path.stem
    path_text = str(profile_path)
    issues: list[ProfileSourceLintIssue] = []

    try:
        with profile_path.open(encoding="utf-8") as handle:
            raw = yaml.safe_load(handle) or {}
    except yaml.YAMLError as exc:
        issues.append(_issue(
            "error",
            "invalid_yaml",
            profile_name,
            path_text,
            "root",
            "",
            f"Profile YAML could not be parsed: {exc}",
            "Fix the YAML syntax, then rerun the source lint report.",
        ))
        return _report(generated_at, profile_name, path_text, issues)

    if not isinstance(raw, dict):
        issues.append(_issue(
            "error",
            "invalid_profile",
            profile_name,
            path_text,
            "root",
            "",
            "Profile root must be a mapping.",
            "Replace the profile contents with a YAML mapping that includes a sources list.",
        ))
        return _report(generated_at, profile_name, path_text, issues)

    declared_name = raw.get("name")
    if isinstance(declared_name, str) and declared_name.strip():
        profile_name = declared_name.strip()

    sources = raw.get("sources", [])
    if not isinstance(sources, list):
        issues.append(_issue(
            "error",
            "invalid_sources",
            profile_name,
            path_text,
            "sources",
            "",
            "Profile sources must be a list.",
            "Change sources to a YAML list of entries with adapter, enabled, and params fields.",
        ))
        return _report(generated_at, profile_name, path_text, issues)

    adapter_indexes: dict[str, list[int]] = defaultdict(list)
    for index, source in enumerate(sources):
        source_path = f"sources[{index}]"
        if not isinstance(source, dict):
            issues.append(_issue(
                "error",
                "invalid_source",
                profile_name,
                path_text,
                source_path,
                "",
                "Source entry must be a mapping.",
                "Replace the source entry with adapter, enabled, and params fields.",
            ))
            continue

        adapter = source.get("adapter")
        adapter_name = adapter if isinstance(adapter, str) else ""
        if not adapter_name:
            issues.append(_issue(
                "error",
                "missing_adapter",
                profile_name,
                path_text,
                f"{source_path}.adapter",
                "",
                "Source entry is missing an adapter name.",
                "Set adapter to one of the registered adapter names.",
            ))
            continue

        adapter_indexes[adapter_name].append(index)
        issues.extend(_lint_source(
            profile_name=profile_name,
            profile_path=path_text,
            source_path=source_path,
            source=source,
            adapter_name=adapter_name,
            metadata=metadata,
        ))

    for adapter, indexes in adapter_indexes.items():
        if len(indexes) <= 1:
            continue
        issue_path = ",".join(f"sources[{index}]" for index in indexes)
        issues.append(_issue(
            "warning",
            "duplicate_adapter",
            profile_name,
            path_text,
            issue_path,
            adapter,
            f"Adapter '{adapter}' appears {len(indexes)} times in this profile.",
            "Merge these entries into one source or make the intended split explicit in adapter params.",
        ))

    issues.sort(key=lambda issue: (_SEVERITY_ORDER[issue.severity], issue.adapter, issue.path))
    return _report(generated_at, profile_name, path_text, issues)


def _lint_source(
    *,
    profile_name: str,
    profile_path: str,
    source_path: str,
    source: dict[str, Any],
    adapter_name: str,
    metadata: dict[str, AdapterMetadata],
) -> list[ProfileSourceLintIssue]:
    issues: list[ProfileSourceLintIssue] = []
    adapter_metadata = metadata.get(adapter_name)
    if adapter_metadata is None:
        issues.append(_issue(
            "error",
            "unknown_adapter",
            profile_name,
            profile_path,
            f"{source_path}.adapter",
            adapter_name,
            f"Adapter '{adapter_name}' is not registered.",
            "Use a registered adapter name or install/register the adapter before enabling this source.",
        ))
        return issues

    enabled = source.get("enabled", True)
    if not isinstance(enabled, bool):
        issues.append(_issue(
            "error",
            "enabled_type_mismatch",
            profile_name,
            profile_path,
            f"{source_path}.enabled",
            adapter_name,
            "Source enabled must be a boolean.",
            "Set enabled to true or false.",
        ))

    params = source.get("params", {})
    if params is None:
        params = {}
    if not isinstance(params, dict):
        issues.append(_issue(
            "error",
            "params_type_mismatch",
            profile_name,
            profile_path,
            f"{source_path}.params",
            adapter_name,
            "Source params must be a mapping.",
            "Change params to a YAML mapping of supported config keys.",
        ))
        return issues

    supported_keys = set(adapter_metadata.config_keys)
    required_keys = set(adapter_metadata.required_keys)
    for key in sorted(set(params) - supported_keys):
        issues.append(_issue(
            "warning",
            "unsupported_param",
            profile_name,
            profile_path,
            f"{source_path}.params.{key}",
            adapter_name,
            f"Param '{key}' is not supported by adapter '{adapter_name}'.",
            f"Remove '{key}' or rename it to one of: {', '.join(adapter_metadata.config_keys) or 'none'}.",
        ))

    missing_required = sorted(key for key in required_keys if key not in params or params[key] is None)
    for key in missing_required:
        issues.append(_issue(
            "error",
            "missing_required_param",
            profile_name,
            profile_path,
            f"{source_path}.params.{key}",
            adapter_name,
            f"Adapter '{adapter_name}' requires params.{key}.",
            f"Add params.{key} with a non-empty value, or disable/remove this source if it should not run.",
        ))

    for key in sorted(required_keys & set(params)):
        value = params[key]
        if isinstance(value, list) and not value:
            issues.append(_issue(
                "error",
                "empty_required_list",
                profile_name,
                profile_path,
                f"{source_path}.params.{key}",
                adapter_name,
                f"Required param '{key}' is an empty list.",
                f"Add at least one value to params.{key}, or remove/disable this source.",
            ))

    for key, value in sorted(params.items()):
        expected = _expected_type_for_param(key)
        if expected is None or value is None:
            continue
        if not _matches_expected_type(value, expected):
            issues.append(_issue(
                "error",
                "param_type_mismatch",
                profile_name,
                profile_path,
                f"{source_path}.params.{key}",
                adapter_name,
                f"Param '{key}' has type {type(value).__name__}; expected {_type_name(expected)}.",
                f"Change params.{key} to {_type_name(expected)}.",
            ))

    if enabled is False and required_keys and not missing_required:
        issues.append(_issue(
            "info",
            "disabled_source_with_required_params",
            profile_name,
            profile_path,
            source_path,
            adapter_name,
            f"Disabled adapter '{adapter_name}' has required params configured but will not fetch.",
            "Set enabled to true when this configured source should participate, or remove it to reduce confusion.",
        ))

    return issues


def _expected_type_for_param(key: str) -> type | tuple[type, ...] | None:
    if key in _COMMON_PARAM_TYPES:
        return _COMMON_PARAM_TYPES[key]
    if key in _LIST_PARAM_KEYS or key.endswith(("ies", "s")):
        return list
    return None


def _matches_expected_type(value: Any, expected: type | tuple[type, ...]) -> bool:
    if expected is bool:
        return isinstance(value, bool)
    if expected is int:
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == (int, float):
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return isinstance(value, expected)


def _type_name(expected: type | tuple[type, ...]) -> str:
    if isinstance(expected, tuple):
        return " or ".join(_type_name(item) for item in expected)
    if expected is list:
        return "a list"
    if expected is dict:
        return "a mapping"
    return expected.__name__


def _report(
    generated_at: str,
    profile_name: str,
    profile_path: str,
    issues: list[ProfileSourceLintIssue],
) -> ProfileSourceLintReport:
    severity_counts = _count_by(issue.severity for issue in issues)
    adapter_counts = _count_by(issue.adapter or "profile" for issue in issues)
    return ProfileSourceLintReport(
        generated_at=generated_at,
        profile_name=profile_name,
        profile_path=profile_path,
        ok=not any(issue.severity == "error" for issue in issues),
        issue_counts_by_severity=severity_counts,
        issue_counts_by_adapter=adapter_counts,
        issues=issues,
    )


def _issue(
    severity: LintSeverity,
    code: str,
    profile_name: str,
    profile_path: str,
    path: str,
    adapter: str,
    message: str,
    suggested_fix: str,
) -> ProfileSourceLintIssue:
    return ProfileSourceLintIssue(
        severity=severity,
        code=code,
        profile_name=profile_name,
        profile_path=profile_path,
        path=path,
        adapter=adapter,
        message=message,
        suggested_fix=suggested_fix,
    )


def _count_by(values) -> dict[str, int]:
    return dict(Counter(values))


def _sum_counts(counts: list[dict[str, int]]) -> dict[str, int]:
    summed: Counter[str] = Counter()
    for count in counts:
        summed.update(count)
    return dict(summed)


def _generated_at() -> str:
    return datetime.now(timezone.utc).isoformat()
