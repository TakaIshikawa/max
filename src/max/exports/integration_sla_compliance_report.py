"""Integration SLA compliance report export."""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.integration_sla_compliance_report.v1"
KIND = "max.integration_sla_compliance_report"
CSV_COLUMNS = ("idea_id", "title", "integration_name", "compliance_status", "uptime_percentage", "sla_target", "incident_count", "p95_latency_ms", "error_rate", "breach_minutes", "dependency_owner", "remediation_plan")
_STATUS_ORDER = {"breached": 0, "warning": 1, "unknown": 2, "compliant": 3}


def build_integration_sla_compliance_report_export(store: Store, domain: str | None = None) -> dict[str, Any]:
    rows = [_row(unit) for unit in store.get_buildable_units(limit=1000, domain=domain)]
    rows.sort(key=lambda row: (_STATUS_ORDER[row["compliance_status"]], -row["breach_minutes"], row["integration_name"], row["idea_id"]))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {"project": "max", "entity_type": "integration_sla_compliance_report", "domain_filter": domain},
        "integration_rows": rows,
        "summary": _summary(rows),
        "breach_totals": {
            "breach_minutes": sum(row["breach_minutes"] for row in rows),
            "incident_count": sum(row["incident_count"] for row in rows),
        },
        "recommendations": _recommendations(rows),
    }


def render_integration_sla_compliance_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_integration_sla_compliance_report_markdown(report: dict[str, Any]) -> str:
    lines = ["# Integration SLA Compliance Report", "", f"Schema: `{report['schema_version']}`", f"Generated: {report['generated_at']}", "", "## Integrations", ""]
    if report.get("integration_rows"):
        lines.extend(["| Integration | Status | Uptime | Target | Incidents | P95 ms | Error Rate | Breach Minutes | Owner |", "|-------------|--------|--------|--------|-----------|--------|------------|----------------|-------|"])
        for row in report["integration_rows"]:
            lines.append(f"| {_md(row['integration_name'])} | {row['compliance_status']} | {row['uptime_percentage']:.2f} | {row['sla_target']:.2f} | {row['incident_count']} | {row['p95_latency_ms']:.0f} | {row['error_rate']:.3f} | {row['breach_minutes']} | {_md(row['dependency_owner'])} |")
    else:
        lines.append("- No integration SLA metadata available.")
    lines.extend(["", "## Recommendations", ""])
    lines.extend(f"- {item}" for item in report.get("recommendations", []))
    return "\n".join(lines).rstrip() + "\n"


def render_integration_sla_compliance_report_csv(report: dict[str, Any]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in report.get("integration_rows", []):
        writer.writerow({column: row.get(column) for column in CSV_COLUMNS})
    return output.getvalue()


def _row(unit: Any) -> dict[str, Any]:
    metadata = _metadata(unit)
    uptime = _float(metadata.get("uptime_percentage"), 0.0)
    target = _float(metadata.get("sla_target"), 99.9)
    incidents = _int(metadata.get("incident_count"), 0)
    latency = _float(metadata.get("p95_latency_ms"), 0.0)
    error_rate = _float(metadata.get("error_rate"), 0.0)
    breach_minutes = _int(metadata.get("breach_minutes"), 0)
    has_metrics = any(key in metadata for key in ("uptime_percentage", "incident_count", "p95_latency_ms", "error_rate", "breach_minutes"))
    status = _status(has_metrics, uptime, target, incidents, latency, error_rate, breach_minutes)
    return {
        "idea_id": str(getattr(unit, "id", "")),
        "title": _text(getattr(unit, "title", "")) or "Untitled",
        "integration_name": _text(metadata.get("integration_name") or metadata.get("integration") or getattr(unit, "title", "Untitled")),
        "compliance_status": status,
        "uptime_percentage": round(uptime, 3),
        "sla_target": round(target, 3),
        "incident_count": incidents,
        "p95_latency_ms": round(latency, 3),
        "error_rate": round(error_rate, 5),
        "breach_minutes": breach_minutes,
        "dependency_owner": _text(metadata.get("dependency_owner") or metadata.get("owner") or "Unassigned"),
        "remediation_plan": _text(metadata.get("remediation_plan") or _remediation(status)),
    }


def _status(has_metrics: bool, uptime: float, target: float, incidents: int, latency: float, error_rate: float, breach_minutes: int) -> str:
    if not has_metrics:
        return "unknown"
    if breach_minutes > 0 or uptime < target or error_rate >= 0.05:
        return "breached"
    if incidents > 0 or latency >= 1000 or error_rate >= 0.02 or uptime < target + 0.05:
        return "warning"
    return "compliant"


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "integration_count": len(rows),
        "status_counts": {status: sum(1 for row in rows if row["compliance_status"] == status) for status in _STATUS_ORDER},
        "average_uptime_percentage": round(sum(row["uptime_percentage"] for row in rows) / len(rows), 3) if rows else 0.0,
    }


def _recommendations(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["Capture integration SLA metrics, owners, and remediation plans for monitored dependencies."]
    if any(row["compliance_status"] == "breached" for row in rows):
        return ["Escalate breached integrations and publish remediation plans with owners."]
    if any(row["compliance_status"] == "warning" for row in rows):
        return ["Review warning integrations before they breach contractual SLA targets."]
    if any(row["compliance_status"] == "unknown" for row in rows):
        return ["Fill missing SLA telemetry for unknown integration rows."]
    return ["Maintain current integration SLA monitoring cadence."]


def _remediation(status: str) -> str:
    if status == "breached":
        return "Open remediation plan and customer communication."
    if status == "warning":
        return "Review trend and prepare preventive mitigation."
    if status == "unknown":
        return "Add SLA telemetry and owner."
    return "Continue monitoring."


def _metadata(unit: Any) -> dict[str, Any]:
    metadata = getattr(unit, "metadata", None)
    return metadata if isinstance(metadata, dict) else {}


def _float(value: Any, default: float) -> float:
    try:
        if value is None or value == "":
            return default
        return max(0.0, float(str(value).rstrip("%")))
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""


def _md(value: Any) -> str:
    return str(value).replace("|", "\\|")
