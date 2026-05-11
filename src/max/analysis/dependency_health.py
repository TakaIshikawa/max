"""Dependency health analysis from package and community signals."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any, Iterable


class HealthRating(StrEnum):
    """Dependency health ratings ordered by operational risk."""

    HEALTHY = "healthy"
    CAUTION = "caution"
    AT_RISK = "at_risk"
    CRITICAL = "critical"


@dataclass(frozen=True)
class DependencyHealth:
    """Health assessment for one technology dependency."""

    name: str
    ecosystem: str
    health_rating: HealthRating
    last_release_days: int | None
    open_issues: int | None
    maintainer_count: int | None
    known_vulnerabilities: int
    community_score: float
    signals_analyzed: int


@dataclass(frozen=True)
class DependencyHealthReport:
    """Aggregated dependency health report for a buildable unit."""

    dependencies: list[DependencyHealth]
    overall_risk: str
    at_risk_count: int
    healthy_count: int


_RATING_ORDER: dict[HealthRating, int] = {
    HealthRating.HEALTHY: 0,
    HealthRating.CAUTION: 1,
    HealthRating.AT_RISK: 2,
    HealthRating.CRITICAL: 3,
}

_CRITICAL_TERMS = {
    "abandoned",
    "critical vulnerability",
    "end of life",
    "unmaintained",
}
_RISK_TERMS = {
    "deprecated",
    "exploit",
    "maintenance mode",
    "security advisory",
    "vulnerable",
}


def assess_dependency_health(name: str, signals: list[dict[str, Any]]) -> DependencyHealth:
    """Assess a dependency from maintenance, security, and community signals."""
    relevant = [signal for signal in signals if _signal_matches(name, signal)]
    if not relevant and signals:
        relevant = signals

    last_release_days = _min_int_field(
        relevant,
        "last_release_days",
        "days_since_release",
        "release_age_days",
    )
    open_issues = _max_int_field(relevant, "open_issues", "issues", "issue_count")
    maintainer_count = _max_int_field(
        relevant,
        "maintainer_count",
        "maintainers",
        "contributors",
    )
    known_vulnerabilities = _sum_int_field(
        relevant,
        "known_vulnerabilities",
        "vulnerabilities",
        "security_advisories",
    )
    community_score = _community_score(relevant)
    ecosystem = _ecosystem(name, relevant)

    risk_score = 0.0
    text = " ".join(_signal_text(signal) for signal in relevant)
    has_critical_language = any(term in text for term in _CRITICAL_TERMS)

    if known_vulnerabilities >= 5:
        risk_score += 4.0
    elif known_vulnerabilities > 0:
        risk_score += 2.0

    if last_release_days is None:
        risk_score += 0.5
    elif last_release_days > 730:
        risk_score += 3.0
    elif last_release_days > 365:
        risk_score += 2.0
    elif last_release_days > 180:
        risk_score += 2.0

    if open_issues is not None:
        if open_issues > 1000:
            risk_score += 2.0
        elif open_issues > 250:
            risk_score += 1.0

    if maintainer_count is None:
        risk_score += 0.5
    elif maintainer_count <= 0:
        risk_score += 3.0
    elif maintainer_count == 1:
        risk_score += 1.5

    if community_score < 0.2:
        risk_score += 1.0
    elif community_score < 0.4:
        risk_score += 0.5

    risk_score += sum(1.0 for term in _RISK_TERMS if term in text)

    if has_critical_language or risk_score >= 6.0:
        rating = HealthRating.CRITICAL
    elif risk_score >= 4.0:
        rating = HealthRating.AT_RISK
    elif risk_score >= 2.0:
        rating = HealthRating.CAUTION
    else:
        rating = HealthRating.HEALTHY

    return DependencyHealth(
        name=name,
        ecosystem=ecosystem,
        health_rating=rating,
        last_release_days=last_release_days,
        open_issues=open_issues,
        maintainer_count=maintainer_count,
        known_vulnerabilities=known_vulnerabilities,
        community_score=community_score,
        signals_analyzed=len(relevant),
    )


def build_dependency_health_report(
    unit: dict[str, Any],
    signals: list[dict[str, Any]],
) -> DependencyHealthReport:
    """Assess all dependencies named in a buildable unit's stack fields."""
    dependencies = [
        assess_dependency_health(name, signals)
        for name in _extract_dependencies(unit)
    ]
    at_risk_count = sum(
        1
        for item in dependencies
        if item.health_rating in {HealthRating.AT_RISK, HealthRating.CRITICAL}
    )
    healthy_count = sum(1 for item in dependencies if item.health_rating == HealthRating.HEALTHY)

    return DependencyHealthReport(
        dependencies=dependencies,
        overall_risk=_overall_risk(dependencies),
        at_risk_count=at_risk_count,
        healthy_count=healthy_count,
    )


def render_dependency_health_markdown(report: DependencyHealthReport) -> str:
    """Render a dependency health report as a Markdown table."""
    lines = [
        "# Dependency Health Report",
        "",
        f"- Overall risk: {report.overall_risk}",
        f"- Healthy dependencies: {report.healthy_count}",
        f"- At-risk dependencies: {report.at_risk_count}",
        "",
        "| Dependency | Ecosystem | Rating | Last Release | Open Issues | Maintainers | Vulnerabilities | Community | Signals |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    if not report.dependencies:
        lines.append("| No dependencies identified | unknown | [gray] n/a |  |  |  | 0 | 0.00 | 0 |")
        return "\n".join(lines) + "\n"

    for dependency in report.dependencies:
        lines.append(
            "| "
            f"{dependency.name} | "
            f"{dependency.ecosystem} | "
            f"{_rating_label(dependency.health_rating)} | "
            f"{_display_int(dependency.last_release_days)} | "
            f"{_display_int(dependency.open_issues)} | "
            f"{_display_int(dependency.maintainer_count)} | "
            f"{dependency.known_vulnerabilities} | "
            f"{dependency.community_score:.2f} | "
            f"{dependency.signals_analyzed} |"
        )
    return "\n".join(lines) + "\n"


def render_dependency_health_json(report: DependencyHealthReport) -> str:
    """Render a dependency health report as stable JSON."""
    payload = asdict(report)
    for dependency in payload["dependencies"]:
        dependency["health_rating"] = dependency["health_rating"].value
    return json.dumps(payload, indent=2, sort_keys=True)


def _extract_dependencies(unit: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("tech_stack", "suggested_stack", "dependencies"):
        values.extend(_dependency_values(unit.get(key)))

    solution = unit.get("solution")
    if isinstance(solution, dict):
        values.extend(_dependency_values(solution.get("suggested_stack")))
        values.extend(_dependency_values(solution.get("tech_stack")))

    return _dedupe(values)


def _dependency_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [_clean_dependency_name(value)] if _clean_dependency_name(value) else []
    if isinstance(value, dict):
        values: list[str] = []
        if "name" in value:
            values.extend(_dependency_values(value["name"]))
        else:
            for item in value.values():
                values.extend(_dependency_values(item))
        return values
    if isinstance(value, Iterable):
        values = []
        for item in value:
            values.extend(_dependency_values(item))
        return values
    return [_clean_dependency_name(str(value))]


def _signal_matches(name: str, signal: dict[str, Any]) -> bool:
    target = _normalize(name)
    candidates: list[str] = []
    for key in ("dependency", "dependency_name", "name", "package", "package_name", "project"):
        value = signal.get(key)
        if value:
            candidates.append(str(value))
    metadata = signal.get("metadata")
    if isinstance(metadata, dict):
        for key in ("dependency", "dependency_name", "name", "package", "package_name", "project"):
            value = metadata.get(key)
            if value:
                candidates.append(str(value))
    candidates.append(_signal_text(signal))
    return any(target and target in _normalize(candidate) for candidate in candidates)


def _ecosystem(name: str, signals: list[dict[str, Any]]) -> str:
    for signal in signals:
        for key in ("ecosystem", "registry", "source"):
            value = signal.get(key)
            if value:
                return str(value)
        metadata = signal.get("metadata")
        if isinstance(metadata, dict):
            for key in ("ecosystem", "registry", "source"):
                value = metadata.get(key)
                if value:
                    return str(value)
    lowered = name.lower()
    if lowered in {"react", "next.js", "typescript", "express"}:
        return "npm"
    if lowered in {"fastapi", "django", "flask", "pandas"}:
        return "pypi"
    if lowered in {"tokio", "serde", "axum"}:
        return "crates"
    return "unknown"


def _overall_risk(dependencies: list[DependencyHealth]) -> str:
    if not dependencies:
        return "unknown"
    worst = max((_RATING_ORDER[item.health_rating] for item in dependencies), default=0)
    if worst >= _RATING_ORDER[HealthRating.CRITICAL]:
        return "critical"
    if worst >= _RATING_ORDER[HealthRating.AT_RISK]:
        return "high"
    if worst >= _RATING_ORDER[HealthRating.CAUTION]:
        return "moderate"
    return "low"


def _community_score(signals: list[dict[str, Any]]) -> float:
    explicit = _max_float_field(signals, "community_score")
    if explicit is not None:
        return round(_clamp(explicit), 4)

    stars = _max_int_field(signals, "stars", "star_count")
    downloads = _max_int_field(signals, "downloads", "weekly_downloads", "monthly_downloads")
    dependents = _max_int_field(signals, "dependents", "dependent_count")
    score = 0.0
    if stars is not None:
        score = max(score, min(0.45, stars / 50_000 * 0.45))
    if downloads is not None:
        score = max(score, min(0.45, downloads / 1_000_000 * 0.45))
    if dependents is not None:
        score = max(score, min(0.35, dependents / 10_000 * 0.35))
    return round(_clamp(score), 4)


def _min_int_field(signals: list[dict[str, Any]], *keys: str) -> int | None:
    values = [_int_value(_nested_get(signal, key)) for signal in signals for key in keys]
    values = [value for value in values if value is not None]
    return min(values) if values else None


def _max_int_field(signals: list[dict[str, Any]], *keys: str) -> int | None:
    values = [_int_value(_nested_get(signal, key)) for signal in signals for key in keys]
    values = [value for value in values if value is not None]
    return max(values) if values else None


def _sum_int_field(signals: list[dict[str, Any]], *keys: str) -> int:
    values = [_int_value(_nested_get(signal, key)) for signal in signals for key in keys]
    return sum(value for value in values if value is not None)


def _max_float_field(signals: list[dict[str, Any]], *keys: str) -> float | None:
    values = [_float_value(_nested_get(signal, key)) for signal in signals for key in keys]
    values = [value for value in values if value is not None]
    return max(values) if values else None


def _nested_get(signal: dict[str, Any], key: str) -> Any:
    if key in signal:
        return signal[key]
    metadata = signal.get("metadata")
    if isinstance(metadata, dict):
        return metadata.get(key)
    return None


def _int_value(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value.replace(",", "")))
        except ValueError:
            return None
    if isinstance(value, list):
        return len(value)
    return None


def _float_value(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(",", ""))
        except ValueError:
            return None
    return None


def _signal_text(signal: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("title", "content", "summary", "description", "body"):
        value = signal.get(key)
        if value:
            parts.append(str(value).lower())
    metadata = signal.get("metadata")
    if isinstance(metadata, dict):
        parts.extend(str(value).lower() for value in metadata.values() if isinstance(value, str))
    return " ".join(parts)


def _clean_dependency_name(value: str) -> str:
    return value.strip().strip(",;")


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = _normalize(value)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(value)
    return sorted(result, key=lambda item: item.lower())


def _normalize(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _rating_label(rating: HealthRating) -> str:
    color = {
        HealthRating.HEALTHY: "green",
        HealthRating.CAUTION: "yellow",
        HealthRating.AT_RISK: "orange",
        HealthRating.CRITICAL: "red",
    }[rating]
    return f"[{color}] {rating.value.replace('_', ' ').title()}"


def _display_int(value: int | None) -> str:
    return "" if value is None else str(value)
