"""Incident impact assessment export for outage review planning."""

from __future__ import annotations

import csv
import io
import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.incident_impact_assessment.v1"
KIND = "max.incident_impact_assessment"
_FIELDS = ["idea_id", "title", "severity", "affected_customers", "downtime_minutes", "revenue_at_risk", "owner", "impact_score", "recovery_priority", "mitigation_gaps"]


def build_incident_impact_assessment_export(store: Store, domain: str | None = None) -> dict[str, Any]:
    units = store.get_buildable_units(limit=1000, domain=domain)
    rows = [_row(unit) for unit in units]
    rows.sort(key=lambda row: (_priority_rank(row["recovery_priority"]), -row["impact_score"], row["idea_id"]))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {"project": "max", "entity_type": "incident_impact_assessment", "domain_filter": domain},
        "incident_row_count": len(rows),
        "incident_rows": rows,
        "summary": _summary(rows),
    }


def render_incident_impact_assessment_markdown(report: dict[str, Any]) -> str:
    lines = ["# Incident Impact Assessment", "", f"Schema: `{report['schema_version']}`", f"Generated: {report['generated_at']}", "", "## Incident Rows", "", "| Unit | Severity | Customers | Downtime | Revenue | Owner | Score | Priority | Gaps |", "|------|----------|-----------|----------|---------|-------|-------|----------|------|"]
    for row in report.get("incident_rows", []):
        lines.append(f"| {row['title']} | {row['severity']} | {row['affected_customers']} | {row['downtime_minutes']} | ${row['revenue_at_risk']:,.0f} | {row['owner']} | {row['impact_score']} | {row['recovery_priority']} | {', '.join(row['mitigation_gaps']) or 'none'} |")
    lines.extend(["", "## Owner Rollup", "", "| Owner | Units | Customers | Revenue |", "|-------|-------|-----------|---------|"])
    for row in report.get("summary", {}).get("by_owner", []):
        lines.append(f"| {row['owner']} | {row['unit_count']} | {row['affected_customers']} | ${row['revenue_at_risk']:,.0f} |")
    return "\n".join(lines).rstrip() + "\n"


def render_incident_impact_assessment_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str)


def render_incident_impact_assessment_csv(report: dict[str, Any]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=_FIELDS)
    writer.writeheader()
    for row in report.get("incident_rows", []):
        writer.writerow({**{field: row.get(field) for field in _FIELDS}, "mitigation_gaps": "; ".join(row.get("mitigation_gaps", []))})
    return output.getvalue()


def _row(unit: Any) -> dict[str, Any]:
    metadata = _metadata(unit)
    affected = int(_float(metadata.get("affected_customers"), 0))
    revenue = max(_float(metadata.get("revenue_at_risk"), 0), 0.0)
    downtime = max(_float(metadata.get("downtime_minutes"), 0), 0.0)
    severity = str(metadata.get("severity") or "sev3").lower()
    owner = str(metadata.get("owner") or "unassigned")
    dependencies = metadata.get("dependencies", [])
    mitigation_status = str(metadata.get("mitigation_status") or "").lower()
    gaps = []
    if owner == "unassigned":
        gaps.append("missing_owner")
    if not dependencies:
        gaps.append("missing_dependencies")
    if mitigation_status not in {"resolved", "mitigated", "complete"}:
        gaps.append("unresolved_mitigation")
    score = _score(severity, affected, revenue, downtime, gaps)
    return {
        "idea_id": str(getattr(unit, "id", "")),
        "title": str(getattr(unit, "title", "Untitled")),
        "severity": severity,
        "affected_customers": affected,
        "downtime_minutes": downtime,
        "revenue_at_risk": round(revenue, 2),
        "owner": owner,
        "impact_score": score,
        "recovery_priority": _priority(score),
        "mitigation_gaps": gaps,
    }


def _score(severity: str, affected: int, revenue: float, downtime: float, gaps: list[str]) -> int:
    score = {"sev1": 50, "critical": 50, "sev2": 35, "high": 35, "sev3": 20, "medium": 20}.get(severity, 10)
    score += min(25, affected // 100)
    score += min(15, int(revenue // 50_000))
    score += min(10, int(downtime // 30))
    score += len(gaps) * 3
    return min(score, 100)


def _priority(score: int) -> str:
    if score >= 70:
        return "critical"
    if score >= 45:
        return "high"
    if score >= 25:
        return "medium"
    return "low"


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_owner = _group(rows, "owner")
    by_severity = _group(rows, "severity")
    return {
        "total_revenue_at_risk": round(sum(row["revenue_at_risk"] for row in rows), 2),
        "total_affected_customers": sum(row["affected_customers"] for row in rows),
        "by_owner": by_owner,
        "by_severity": by_severity,
    }


def _group(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[row[key]].append(row)
    return [{key: name, "unit_count": len(items), "affected_customers": sum(row["affected_customers"] for row in items), "revenue_at_risk": round(sum(row["revenue_at_risk"] for row in items), 2)} for name, items in sorted(groups.items())]


def _metadata(unit: Any) -> dict[str, Any]:
    metadata = getattr(unit, "metadata", None)
    return metadata if isinstance(metadata, dict) else {}


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _priority_rank(value: str) -> int:
    return {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(value, 4)
