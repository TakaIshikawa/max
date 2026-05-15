"""Customer journey friction report export for lifecycle review."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.customer_journey_friction_report.v1"
KIND = "max.customer_journey_friction_report"

_STAGE_ORDER = {"discovery": 0, "onboarding": 1, "adoption": 2, "support": 3, "renewal": 4, "expansion": 5, "unknown": 6}
_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
_STAGE_ALIASES = {
    "evaluation": "discovery",
    "trial": "discovery",
    "implementation": "onboarding",
    "activation": "onboarding",
    "usage": "adoption",
    "customer_support": "support",
    "success": "support",
    "retention": "renewal",
    "upsell": "expansion",
}


def build_customer_journey_friction_report_export(store: Store, domain: str | None = None) -> dict[str, Any]:
    """Build a customer journey friction report from buildable unit evidence."""
    units = store.get_buildable_units(limit=1000, domain=domain)
    points = [_friction_point(unit) for unit in units]
    points.sort(key=lambda point: (_STAGE_ORDER[point["stage"]], _SEVERITY_ORDER[point["severity"]], -point["severity_score"], point["title"], point["idea_id"]))
    stages = _stage_groups(points)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {"project": "max", "entity_type": "customer_journey_friction_report", "domain_filter": domain},
        "summary": _summary(points, stages),
        "stages": stages,
        "friction_points": points,
        "recommendations": _recommendations(points),
    }


def render_customer_journey_friction_report_markdown(report: dict[str, Any]) -> str:
    """Render a customer journey friction report as Markdown."""
    summary = report.get("summary", {})
    lines = [
        "# Customer Journey Friction Report",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Generated: {report['generated_at']}",
        "",
        "## Summary",
        "",
        f"- Friction points: {summary.get('friction_point_count', 0)}",
        f"- Highest severity: {summary.get('highest_severity', 'low')}",
        f"- Average severity score: {summary.get('average_severity_score', 0.0):.1f}",
        "",
        "## Lifecycle Stages",
        "",
    ]
    if report.get("stages"):
        for stage in report["stages"]:
            lines.extend([
                f"### {stage['stage_label']}",
                "",
                f"- Points: {stage['friction_point_count']}",
                f"- Highest severity: {stage['highest_severity']}",
                "",
                "| Friction | Severity | Impact | Evidence | Recommendation |",
                "|----------|----------|--------|----------|----------------|",
            ])
            for point in stage["friction_points"]:
                lines.append(
                    f"| {_md(point['title'])} | {point['severity']} | {_md(point['impact'])} | "
                    f"{_md(', '.join(point['evidence_references']) or 'No explicit references')} | "
                    f"{_md(point['recommended_action'])} |"
                )
                lines.append("")
    else:
        lines.append("- No lifecycle evidence found. Add onboarding, support, adoption, or renewal signals to identify friction.")
    lines.extend(["## Recommendations", ""])
    for recommendation in report.get("recommendations", []):
        lines.append(f"- {recommendation}")
    return "\n".join(lines).rstrip() + "\n"


def render_customer_journey_friction_report_json(report: dict[str, Any]) -> str:
    """Render a customer journey friction report as stable formatted JSON."""
    return json.dumps(report, indent=2, sort_keys=True, default=str)


def _friction_point(unit: Any) -> dict[str, Any]:
    metadata = _metadata(unit)
    stage = _stage(_first(metadata, "journey_stage", "lifecycle_stage", "stage", "customer_stage"))
    evidence = _list(_first(metadata, "evidence_references", "evidence", "support_tickets", "onboarding_notes", "adoption_signals"))
    drivers = _drivers(metadata)
    score = _severity_score(metadata, evidence, drivers)
    severity = _severity(score)
    impact = _impact(metadata, severity, drivers)
    return {
        "idea_id": str(getattr(unit, "id", "")),
        "title": _text(_first(metadata, "friction", "friction_point", "issue")) or str(getattr(unit, "title", "Untitled")),
        "stage": stage,
        "stage_label": _label(stage),
        "severity": severity,
        "severity_score": score,
        "impact": impact,
        "drivers": drivers,
        "evidence_references": evidence,
        "recommended_action": _recommended_action(stage, severity, drivers),
    }


def _stage_groups(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for point in points:
        grouped[point["stage"]].append(point)
    stages = []
    for stage, items in grouped.items():
        stages.append({
            "stage": stage,
            "stage_label": _label(stage),
            "friction_point_count": len(items),
            "highest_severity": min((item["severity"] for item in items), key=_SEVERITY_ORDER.get),
            "average_severity_score": round(sum(item["severity_score"] for item in items) / len(items), 1),
            "friction_points": items,
        })
    return sorted(stages, key=lambda row: _STAGE_ORDER[row["stage"]])


def _summary(points: list[dict[str, Any]], stages: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(point["severity"] for point in points)
    return {
        "friction_point_count": len(points),
        "stage_count": len(stages),
        "highest_severity": min((point["severity"] for point in points), key=_SEVERITY_ORDER.get) if points else "low",
        "average_severity_score": round(sum(point["severity_score"] for point in points) / len(points), 1) if points else 0.0,
        "severity_counts": {severity: counts.get(severity, 0) for severity in ("critical", "high", "medium", "low")},
    }


def _recommendations(points: list[dict[str, Any]]) -> list[str]:
    if not points:
        return ["Capture lifecycle stage, impact, and evidence references before the next journey review."]
    if any(point["severity"] in {"critical", "high"} for point in points):
        return ["Assign owners to high-severity journey friction and review progress in the next customer success operating cadence."]
    return ["Keep evidence references current and monitor recurring journey friction by stage."]


def _drivers(metadata: dict[str, Any]) -> list[str]:
    values = _list(_first(metadata, "drivers", "friction_drivers", "blockers", "pain_points"))
    if values:
        return values
    derived = []
    if _text(_first(metadata, "support_load", "open_tickets", "escalations")):
        derived.append("Support load")
    if _text(_first(metadata, "onboarding_delay", "implementation_delay")):
        derived.append("Onboarding delay")
    if _text(_first(metadata, "adoption_gap", "usage_gap")):
        derived.append("Adoption gap")
    return derived


def _severity_score(metadata: dict[str, Any], evidence: list[str], drivers: list[str]) -> float:
    explicit = _number(_first(metadata, "severity_score", "friction_score", "impact_score"))
    if explicit is not None:
        return explicit
    text = _text(_first(metadata, "severity", "impact", "support_load", "escalations")).lower()
    base = 20.0
    if any(word in text for word in ("critical", "blocked", "churn", "escalation", "sev1")):
        base = 90.0
    elif any(word in text for word in ("high", "late", "at risk", "many")):
        base = 75.0
    elif any(word in text for word in ("medium", "moderate", "some")):
        base = 50.0
    elif any(word in text for word in ("low", "minor")):
        base = 25.0
    base += min(len(evidence), 3) * 3
    base += min(len(drivers), 3) * 4
    return round(min(base, 100.0), 1)


def _severity(score: float) -> str:
    return "critical" if score >= 90 else "high" if score >= 70 else "medium" if score >= 40 else "low"


def _impact(metadata: dict[str, Any], severity: str, drivers: list[str]) -> str:
    explicit = _text(_first(metadata, "impact", "customer_impact", "business_impact"))
    if explicit:
        return explicit
    if drivers:
        return f"{severity.title()} journey risk from {drivers[0].lower()}."
    return f"{severity.title()} lifecycle friction with limited evidence."


def _recommended_action(stage: str, severity: str, drivers: list[str]) -> str:
    focus = drivers[0].lower() if drivers else f"{stage} evidence"
    if severity in {"critical", "high"}:
        return f"Create an owner-backed mitigation for {focus}."
    return f"Track {focus} in the next lifecycle review."


def _metadata(unit: Any) -> dict[str, Any]:
    metadata = getattr(unit, "metadata", None)
    return metadata if isinstance(metadata, dict) else {}


def _first(metadata: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in metadata:
            return metadata[key]
    for value in metadata.values():
        if isinstance(value, dict):
            found = _first(value, *keys)
            if found not in (None, ""):
                return found
    return None


def _stage(value: Any) -> str:
    stage = _text(value).lower().replace(" ", "_").replace("-", "_") or "unknown"
    return _STAGE_ALIASES.get(stage, stage if stage in _STAGE_ORDER else "unknown")


def _list(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, dict):
        return [f"{key}: {_text(val)}" for key, val in sorted(value.items()) if _text(val)]
    if isinstance(value, (list, tuple, set)):
        return [_text(item) for item in value if _text(item)]
    return [_text(value)]


def _number(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return max(0.0, min(float(value), 100.0))
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""


def _label(value: str) -> str:
    return value.replace("_", " ").title()


def _md(value: Any) -> str:
    return str(value).replace("|", "\\|")
