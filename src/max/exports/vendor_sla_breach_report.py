"""Vendor SLA breach report export."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Iterable, Literal, TypedDict

SCHEMA_VERSION = "max.vendor_sla_breach_report.v1"
KIND = "max.vendor_sla_breach_report"

Severity = Literal["critical", "high", "medium", "low", "unknown"]
BreachStatus = Literal["active", "monitoring", "resolved"]
GroupBy = Literal["vendor", "owner", "service"]


class VendorSlaBreachInput(TypedDict, total=False):
    vendor: str
    service: str
    metric: str
    breached_metric: str
    duration: str
    impact: str
    severity: str
    status: str
    owner: str
    next_action: str
    action: str
    detected_at: str


def build_vendor_sla_breach_report(
    records: Iterable[VendorSlaBreachInput | dict[str, Any]],
    *,
    title: str = "Vendor SLA Breach Report",
    group_by: GroupBy = "vendor",
) -> dict[str, Any]:
    breaches = _normalize_breaches(records)
    groups = _groups(breaches, group_by)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "title": _text(title) or "Vendor SLA Breach Report",
        "group_by": group_by,
        "summary": _summary(breaches, groups),
        "groups": groups,
        "breaches": breaches,
    }


def render_vendor_sla_breach_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        f"# {report.get('title') or 'Vendor SLA Breach Report'}",
        "",
        f"Schema: `{report.get('schema_version', SCHEMA_VERSION)}`",
        "",
        "## Summary",
        "",
        f"- Total breaches: {summary.get('breach_count', 0)}",
        f"- Active breaches: {summary.get('active_count', 0)}",
        f"- Critical/high severity: {summary.get('critical_high_count', 0)}",
        f"- Vendors affected: {summary.get('vendor_count', 0)}",
        "",
        "## Breach Register",
        "",
    ]
    groups = report.get("groups") or []
    if groups:
        for group in groups:
            lines.extend([f"### {group['name']}", ""])
            for breach in group["breaches"]:
                lines.extend(
                    [
                        f"#### {breach['vendor']} - {breach['service']}",
                        f"- Status: {breach['status']}",
                        f"- Severity: {breach['severity']}",
                        f"- Breached metric: {breach['breached_metric']}",
                        f"- Duration: {breach['duration']}",
                        f"- Impact: {breach['impact']}",
                        f"- Owner: {breach['owner']}",
                        f"- Next action: {breach['next_action']}",
                        "",
                    ]
                )
    else:
        lines.append("- No vendor SLA breaches were supplied.")
    return "\n".join(lines).rstrip() + "\n"


def render_vendor_sla_breach_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def _normalize_breaches(records: Iterable[VendorSlaBreachInput | dict[str, Any]]) -> list[dict[str, Any]]:
    breaches = [
        {
            "vendor": _text(raw.get("vendor") or "Unspecified vendor"),
            "service": _text(raw.get("service") or "Unspecified service"),
            "breached_metric": _text(raw.get("breached_metric") or raw.get("metric") or "Unspecified metric"),
            "duration": _text(raw.get("duration") or "Unspecified duration"),
            "impact": _text(raw.get("impact") or "Impact not supplied"),
            "severity": _severity(raw.get("severity")),
            "status": _status(raw.get("status")),
            "owner": _text(raw.get("owner") or "Unassigned"),
            "next_action": _text(raw.get("next_action") or raw.get("action") or "Confirm owner, remediation ETA, and customer impact."),
            "detected_at": _text(raw.get("detected_at")),
        }
        for raw in records
    ]
    breaches.sort(key=_breach_sort_key)
    return breaches


def _groups(breaches: list[dict[str, Any]], group_by: GroupBy) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for breach in breaches:
        grouped[breach[group_by]].append(breach)
    rows = [{"name": name, "breach_count": len(items), "breaches": items} for name, items in grouped.items()]
    rows.sort(key=lambda row: (_group_worst_key(row["breaches"]), row["name"].lower()))
    return rows


def _summary(breaches: list[dict[str, Any]], groups: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "breach_count": len(breaches),
        "group_count": len(groups),
        "vendor_count": len({breach["vendor"] for breach in breaches}),
        "active_count": sum(1 for breach in breaches if breach["status"] == "active"),
        "critical_high_count": sum(1 for breach in breaches if breach["severity"] in {"critical", "high"}),
    }


_STATUS_ORDER = {"active": 0, "monitoring": 1, "resolved": 2}
_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "unknown": 4}


def _breach_sort_key(breach: dict[str, Any]) -> tuple[int, int, str, str, str]:
    return (
        _STATUS_ORDER[breach["status"]],
        _SEVERITY_ORDER[breach["severity"]],
        breach["detected_at"] or "9999-12-31",
        breach["vendor"].lower(),
        breach["service"].lower(),
    )


def _group_worst_key(breaches: list[dict[str, Any]]) -> tuple[int, int, str]:
    first = min(breaches, key=_breach_sort_key)
    return (_STATUS_ORDER[first["status"]], _SEVERITY_ORDER[first["severity"]], first["detected_at"] or "9999-12-31")


def _status(value: Any) -> BreachStatus:
    text = _text(value).lower()
    if text in {"resolved", "closed", "remediated"}:
        return "resolved"
    if text in {"monitoring", "watching", "mitigated"}:
        return "monitoring"
    return "active"


def _severity(value: Any) -> Severity:
    text = _text(value).lower()
    if text in _SEVERITY_ORDER:
        return text  # type: ignore[return-value]
    return "unknown"


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
