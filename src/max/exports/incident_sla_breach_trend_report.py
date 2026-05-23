"""Incident SLA breach trend export report."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.incident_sla_breach_trend_report.v1"
KIND = "max.incident_sla_breach_trend_report"

_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "unknown": 4}


def build_incident_sla_breach_trend_report_export(store: Store, domain: str | None = None) -> dict[str, Any]:
    rows = [_row(unit) for unit in store.get_buildable_units(limit=1000, domain=domain)]
    rows.sort(key=lambda row: (_SEVERITY_ORDER[row["severity"]], -row["breach_duration_minutes"], row["period"], row["incident_id"]))
    trends = _trends(rows)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {"project": "max", "entity_type": "incident_sla_breach_trend_report", "domain_filter": domain},
        "summary": _summary(rows, trends),
        "incident_rows": rows,
        "trend_buckets": trends,
        "corrective_actions": _actions(rows, trends),
    }


def render_incident_sla_breach_trend_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str)


def render_incident_sla_breach_trend_report_markdown(report: dict[str, Any]) -> str:
    lines = ["# Incident SLA Breach Trend Report", "", f"Schema: `{report['schema_version']}`", f"Generated: {report['generated_at']}", "", "## Trend Buckets", ""]
    if report.get("trend_buckets"):
        lines.extend(["| Period | Severity | Breaches | Minutes | Trend |", "|--------|----------|----------|---------|-------|"])
        for row in report["trend_buckets"]:
            lines.append(f"| {_md(row['period'])} | {row['severity']} | {row['breach_count']} | {row['total_breach_minutes']} | {row['trend']} |")
    else:
        lines.append("- No incident SLA breach records found.")
    lines.extend(["", "## Corrective Actions", ""])
    for action in report.get("corrective_actions", []):
        lines.append(f"- {action}")
    return "\n".join(lines).rstrip() + "\n"


def _row(unit: Any) -> dict[str, Any]:
    m = _metadata(unit)
    duration = _number(m.get("breach_duration_minutes") or m.get("breach_minutes"))
    return {
        "incident_id": _text(m.get("incident_id") or getattr(unit, "id", "")),
        "title": _text(m.get("title") or getattr(unit, "title", "Untitled")),
        "sla_target": _text(m.get("sla_target") or "not recorded"),
        "breach_duration_minutes": round(duration, 1),
        "severity": _severity(m.get("severity")),
        "customer_impact": _text(m.get("customer_impact") or "not recorded"),
        "period": _text(m.get("period") or m.get("detected_month") or "unbucketed"),
        "corrective_action": _text(m.get("corrective_action") or "Review SLA breach cause and owner."),
    }


def _trends(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["period"], row["severity"])].append(row)
    result = []
    for (period, severity), items in grouped.items():
        result.append({"period": period, "severity": severity, "breach_count": len(items), "total_breach_minutes": round(sum(row["breach_duration_minutes"] for row in items), 1), "trend": "worsening" if len(items) > 1 or sum(row["breach_duration_minutes"] for row in items) >= 120 else "watch"})
    return sorted(result, key=lambda row: (row["period"], _SEVERITY_ORDER[row["severity"]]))


def _summary(rows: list[dict[str, Any]], trends: list[dict[str, Any]]) -> dict[str, Any]:
    return {"incident_count": len(rows), "breach_count": sum(1 for row in rows if row["breach_duration_minutes"] > 0), "total_breach_minutes": round(sum(row["breach_duration_minutes"] for row in rows), 1), "trend_bucket_count": len(trends), "severity_counts": {severity: sum(1 for row in rows if row["severity"] == severity) for severity in _SEVERITY_ORDER}}


def _actions(rows: list[dict[str, Any]], trends: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["Capture incident SLA targets, breach duration, severity, and corrective action."]
    actions = sorted({row["corrective_action"] for row in rows if row["corrective_action"]}, key=str.lower)
    if any(row["trend"] == "worsening" for row in trends):
        actions.insert(0, "Escalate worsening SLA breach trend to incident leadership.")
    return actions


def _severity(value: Any) -> str:
    text = _text(value).lower()
    return text if text in _SEVERITY_ORDER else "unknown"


def _metadata(unit: Any) -> dict[str, Any]:
    return getattr(unit, "metadata", None) if isinstance(getattr(unit, "metadata", None), dict) else {}


def _number(value: Any) -> float:
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return 0.0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""


def _md(value: Any) -> str:
    return str(value).replace("|", "\\|")
