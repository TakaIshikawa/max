"""Implementation risk heatmap export for delivery planning."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.implementation_risk_heatmap.v1"
KIND = "max.implementation_risk_heatmap"

_DIMENSIONS = [
    "engineering_effort",
    "dependency_count",
    "unknowns",
    "security_complexity",
    "data_migration_required",
    "team_readiness",
    "deadline_pressure",
]
_DIMENSION_LABELS = {
    "engineering_effort": "Engineering effort",
    "dependency_count": "Dependency count",
    "unknowns": "Implementation unknowns",
    "security_complexity": "Security complexity",
    "data_migration_required": "Data migration required",
    "team_readiness": "Team readiness",
    "deadline_pressure": "Deadline pressure",
}
_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}
_RISK_WORDS = {
    "none": 0.0,
    "no": 0.0,
    "false": 0.0,
    "low": 20.0,
    "small": 20.0,
    "simple": 20.0,
    "ready": 15.0,
    "medium": 55.0,
    "moderate": 55.0,
    "partial": 55.0,
    "some": 55.0,
    "high": 80.0,
    "large": 80.0,
    "complex": 80.0,
    "true": 80.0,
    "yes": 80.0,
    "required": 80.0,
    "critical": 95.0,
    "blocked": 95.0,
}
_READINESS_WORDS = {
    "ready": 15.0,
    "high": 20.0,
    "strong": 20.0,
    "medium": 45.0,
    "partial": 55.0,
    "low": 80.0,
    "not_ready": 90.0,
    "unready": 90.0,
    "blocked": 95.0,
}


def build_implementation_risk_heatmap_export(
    store: Store,
    domain: str | None = None,
) -> dict[str, Any]:
    """Score buildable units for delivery implementation risk."""
    units = store.get_buildable_units(limit=1000, domain=domain)
    rows = [_risk_row(unit) for unit in units]
    rows.sort(key=lambda row: (_SEVERITY_ORDER[row["severity"]], -row["total_risk_score"], row["title"], row["idea_id"]))
    summary = _summary(rows)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "project": "max",
            "entity_type": "implementation_risk_heatmap",
            "domain_filter": domain,
            "defaults": {
                "missing_dimension_score": 0.0,
                "low_threshold": 40.0,
                "high_threshold": 70.0,
            },
        },
        "summary": summary,
        "risk_rows": rows,
        "recommendations": _recommendations(rows, summary),
    }


def render_implementation_risk_heatmap_markdown(report: dict[str, Any]) -> str:
    """Render implementation risk heatmap as Markdown."""
    summary = report.get("summary", {})
    lines = [
        "# Implementation Risk Heatmap",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Generated: {report['generated_at']}",
        "",
        "## Summary",
        "",
        f"- Ideas analyzed: {summary.get('idea_count', 0)}",
        f"- Average risk score: {summary.get('average_risk_score', 0.0):.1f}",
        f"- High risk: {summary.get('severity_counts', {}).get('high', 0)}",
        f"- Medium risk: {summary.get('severity_counts', {}).get('medium', 0)}",
        f"- Low risk: {summary.get('severity_counts', {}).get('low', 0)}",
        "",
        "## Heatmap",
        "",
    ]
    if report.get("risk_rows"):
        lines.extend([
            "| Idea | Severity | Score | Effort | Deps | Unknowns | Security | Migration | Readiness | Deadline | Drivers | Mitigation |",
            "|------|----------|-------|--------|------|----------|----------|-----------|-----------|----------|---------|------------|",
        ])
        for row in report["risk_rows"]:
            scores = row["dimension_scores"]
            lines.append(
                f"| {_md(row['title'])} | {row['severity']} | {row['total_risk_score']:.1f} | "
                f"{scores['engineering_effort']:.0f} | {scores['dependency_count']:.0f} | "
                f"{scores['unknowns']:.0f} | {scores['security_complexity']:.0f} | "
                f"{scores['data_migration_required']:.0f} | {scores['team_readiness']:.0f} | "
                f"{scores['deadline_pressure']:.0f} | {_md(', '.join(row['risk_drivers']) or 'None')} | "
                f"{_md(row['recommended_mitigation'])} |"
            )
    else:
        lines.append(
            "- No buildable units found. Add implementation metadata such as engineering_effort, "
            "dependency_count, unknowns, team_readiness, and deadline_pressure to generate a heatmap."
        )

    lines.extend(["", "## Top Risk Drivers", ""])
    if summary.get("top_risk_drivers"):
        for driver in summary["top_risk_drivers"]:
            lines.append(f"- {driver['driver']}: {driver['count']}")
    else:
        lines.append("- No recurring risk drivers identified.")

    lines.extend(["", "## Recommendations", ""])
    for recommendation in report.get("recommendations", []):
        lines.append(f"- {recommendation}")
    return "\n".join(lines).rstrip() + "\n"


def render_implementation_risk_heatmap_json(report: dict[str, Any]) -> str:
    """Render implementation risk heatmap as stable formatted JSON."""
    return json.dumps(report, indent=2, sort_keys=True, default=str)


def _risk_row(unit: Any) -> dict[str, Any]:
    metadata = _metadata(unit)
    dimension_scores = {dimension: _dimension_score(metadata, dimension) for dimension in _DIMENSIONS}
    total_score = round(sum(dimension_scores.values()) / len(dimension_scores), 1)
    severity = _severity(total_score)
    drivers = _drivers(dimension_scores)
    return {
        "idea_id": str(getattr(unit, "id", "")),
        "title": str(getattr(unit, "title", "Untitled")),
        "severity": severity,
        "total_risk_score": total_score,
        "dimension_scores": dimension_scores,
        "risk_drivers": drivers,
        "recommended_mitigation": _mitigation(severity, drivers),
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    severity_counts = {severity: sum(1 for row in rows if row["severity"] == severity) for severity in ("high", "medium", "low")}
    driver_counts = Counter(driver for row in rows for driver in row["risk_drivers"])
    top_drivers = [
        {"driver": driver, "count": count}
        for driver, count in sorted(driver_counts.items(), key=lambda item: (-item[1], item[0]))
    ][:5]
    return {
        "idea_count": len(rows),
        "average_risk_score": round(sum(row["total_risk_score"] for row in rows) / len(rows), 1) if rows else 0.0,
        "severity_counts": severity_counts,
        "top_risk_drivers": top_drivers,
    }


def _recommendations(rows: list[dict[str, Any]], summary: dict[str, Any]) -> list[str]:
    if not rows:
        return [
            "Add implementation risk metadata to buildable units before delivery planning.",
            "Capture dependencies, unknowns, readiness, and deadline pressure for each candidate idea.",
        ]
    recommendations: list[str] = []
    if summary["severity_counts"]["high"]:
        recommendations.append("Review high-risk units in delivery planning and assign mitigation owners before committing dates.")
    if any("Dependency count" in row["risk_drivers"] for row in rows):
        recommendations.append("Split external dependencies into named owners, due dates, and fallback paths.")
    if any("Implementation unknowns" in row["risk_drivers"] for row in rows):
        recommendations.append("Run discovery spikes for units with unresolved implementation unknowns.")
    if not recommendations:
        recommendations.append("Keep implementation risk metadata current as scope and launch dates change.")
    return recommendations


def _dimension_score(metadata: dict[str, Any], dimension: str) -> float:
    value = _lookup(metadata, dimension)
    if value in (None, ""):
        return 0.0
    if dimension == "dependency_count":
        return _dependency_score(value)
    if dimension == "unknowns":
        return _unknowns_score(value)
    if dimension == "team_readiness":
        return _team_readiness_score(value)
    if dimension == "data_migration_required":
        return _boolean_risk_score(value)
    if isinstance(value, bool):
        return 80.0 if value else 10.0
    number = _coerce_float(value)
    if number is not None:
        return _bounded(number)
    return _word_score(value)


def _dependency_score(value: Any) -> float:
    if isinstance(value, (list, tuple, set)):
        return _bounded(len(value) * 15.0)
    number = _coerce_float(value)
    if number is not None:
        return _bounded(number * 15.0 if number <= 10 else number)
    return _word_score(value)


def _unknowns_score(value: Any) -> float:
    if isinstance(value, (list, tuple, set)):
        return _bounded(len([item for item in value if str(item).strip()]) * 20.0)
    if isinstance(value, bool):
        return 70.0 if value else 0.0
    number = _coerce_float(value)
    if number is not None:
        return _bounded(number * 20.0 if number <= 5 else number)
    text = str(value).strip()
    if "," in text or ";" in text:
        return _bounded(len([item for item in text.replace(";", ",").split(",") if item.strip()]) * 20.0)
    return _word_score(value)


def _team_readiness_score(value: Any) -> float:
    if isinstance(value, bool):
        return 15.0 if value else 90.0
    number = _coerce_float(value)
    if number is not None:
        return _bounded(100.0 - number if number <= 100 else 0.0)
    normalized = _normalize_word(value)
    return _READINESS_WORDS.get(normalized, 55.0)


def _boolean_risk_score(value: Any) -> float:
    if isinstance(value, bool):
        return 80.0 if value else 0.0
    number = _coerce_float(value)
    if number is not None:
        return 80.0 if number > 0 else 0.0
    return _word_score(value)


def _drivers(dimension_scores: dict[str, float]) -> list[str]:
    drivers = [
        _DIMENSION_LABELS[dimension]
        for dimension, score in sorted(dimension_scores.items(), key=lambda item: (-item[1], _DIMENSION_LABELS[item[0]]))
        if score >= 60.0
    ]
    return drivers[:3]


def _severity(score: float) -> str:
    if score >= 70.0:
        return "high"
    if score >= 40.0:
        return "medium"
    return "low"


def _mitigation(severity: str, drivers: list[str]) -> str:
    if not drivers:
        return "Monitor delivery metadata and revisit if scope changes."
    primary = drivers[0]
    if severity == "high":
        return f"Assign an owner to reduce {primary.lower()} before delivery commitment."
    if severity == "medium":
        return f"Create a mitigation checkpoint for {primary.lower()} during planning."
    return f"Track {primary.lower()} in the delivery plan."


def _metadata(unit: Any) -> dict[str, Any]:
    metadata = getattr(unit, "metadata", None)
    if isinstance(metadata, dict):
        return metadata
    extra = getattr(unit, "extra", None)
    return extra if isinstance(extra, dict) else {}


def _lookup(metadata: dict[str, Any], key: str) -> Any:
    if key in metadata:
        return metadata[key]
    for nested_key in ("implementation", "delivery", "risk", "execution"):
        nested = metadata.get(nested_key)
        if isinstance(nested, dict) and key in nested:
            return nested[key]
    return None


def _word_score(value: Any) -> float:
    return _RISK_WORDS.get(_normalize_word(value), 55.0)


def _normalize_word(value: Any) -> str:
    return str(value).strip().lower().replace("-", "_").replace(" ", "_")


def _coerce_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        return float(str(value).replace(",", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return None


def _bounded(value: float) -> float:
    return round(min(max(value, 0.0), 100.0), 1)


def _md(value: Any) -> str:
    return str(value).replace("|", "\\|")
