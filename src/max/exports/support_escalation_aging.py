"""Support escalation aging export."""

from __future__ import annotations

import csv
import io
import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.support_escalation_aging.v1"
KIND = "max.support_escalation_aging"
CSV_FIELDS = ("idea_id", "title", "account_name", "customer_segment", "support_ticket_count", "escalated_ticket_count", "oldest_ticket_age_days", "sla_target_days", "severity", "aging_band", "last_customer_update_at", "next_action")
_BAND_ORDER = {"critical": 0, "overdue": 1, "watchlist": 2, "on_track": 3}


def build_support_escalation_aging_export(store: Store, domain: str | None = None) -> dict[str, Any]:
    rows = [_row(unit) for unit in store.get_buildable_units(limit=1000, domain=domain)]
    rows.sort(key=lambda row: (_BAND_ORDER[row["aging_band"]], -row["oldest_ticket_age_days"], row["account_name"].lower(), row["idea_id"]))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "generated_at": datetime.now(timezone.utc).isoformat(), "source": {"project": "max", "entity_type": "support_escalation_aging", "domain_filter": domain}, "escalations": rows, "summary": _summary(rows), "recommendations": _recommendations(rows)}


def render_support_escalation_aging_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str)


def render_support_escalation_aging_csv(report: dict[str, Any]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    for row in report.get("escalations", []):
        writer.writerow({field: row.get(field) for field in CSV_FIELDS})
    return output.getvalue()


def render_support_escalation_aging_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = ["# Support Escalation Aging", "", f"Schema: `{report['schema_version']}`", f"Generated: {report['generated_at']}", "", "## Summary", "", f"- Escalations reviewed: {summary.get('escalation_count', 0)}", f"- Critical: {summary.get('band_counts', {}).get('critical', 0)}", f"- Overdue: {summary.get('band_counts', {}).get('overdue', 0)}", f"- Average age: {summary.get('average_age_days', 0.0):.1f} days", "", "## Escalations", ""]
    if report.get("escalations"):
        lines.extend(["| Account | Segment | Age | SLA | Severity | Band | Next Action |", "|---------|---------|-----|-----|----------|------|-------------|"])
        for row in report["escalations"]:
            lines.append(f"| {_md(row['account_name'])} | {_md(row['customer_segment'])} | {row['oldest_ticket_age_days']} | {row['sla_target_days']} | {row['severity']} | {row['aging_band']} | {_md(row['next_action'])} |")
    else:
        lines.append("- No support escalation metadata found.")
    lines.extend(["", "## Segment Rollup", ""])
    for item in summary.get("by_segment", []):
        lines.append(f"- {item['customer_segment']}: {item['escalation_count']} escalation(s), oldest {item['oldest_ticket_age_days']} day(s)")
    lines.extend(["", "## Recommendations", ""])
    lines.extend(f"- {item}" for item in report.get("recommendations", []))
    return "\n".join(lines).rstrip() + "\n"


def _row(unit: Any) -> dict[str, Any]:
    metadata = _metadata(unit)
    tickets = _int(_number(metadata, "support_ticket_count", 0))
    escalated = _int(_number(metadata, "escalated_ticket_count", tickets if tickets else 0))
    age = _int(_number(metadata, "oldest_ticket_age_days", 0))
    sla = max(_int(_number(metadata, "sla_target_days", 7)), 1)
    severity = str(metadata.get("severity") or "medium").lower()
    band = _band(age, sla, severity, escalated)
    return {"idea_id": str(getattr(unit, "id", "")), "title": str(getattr(unit, "title", "Untitled")), "domain": str(getattr(unit, "domain", "") or "general"), "account_name": str(metadata.get("account_name") or getattr(unit, "title", "Unknown account")), "customer_segment": str(metadata.get("customer_segment") or metadata.get("segment") or "unknown").lower(), "support_ticket_count": tickets, "escalated_ticket_count": escalated, "oldest_ticket_age_days": age, "sla_target_days": sla, "severity": severity, "last_customer_update_at": str(metadata.get("last_customer_update_at") or ""), "blocker_notes": _items(metadata.get("blocker_notes")), "aging_band": band, "next_action": _next_action(band)}


def _band(age: int, sla: int, severity: str, escalated: int) -> str:
    if escalated and (age >= sla * 2 or severity in {"critical", "sev1", "p0"}):
        return "critical"
    if age > sla:
        return "overdue"
    if escalated or age >= max(sla - 1, 1) or severity in {"high", "sev2", "p1"}:
        return "watchlist"
    return "on_track"


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[row["customer_segment"]].append(row)
    return {"escalation_count": len(rows), "band_counts": {band: sum(1 for row in rows if row["aging_band"] == band) for band in _BAND_ORDER}, "oldest_escalation_age_days": max((row["oldest_ticket_age_days"] for row in rows), default=0), "average_age_days": round(sum(row["oldest_ticket_age_days"] for row in rows) / len(rows), 1) if rows else 0.0, "by_segment": [{"customer_segment": segment, "escalation_count": len(items), "oldest_ticket_age_days": max(item["oldest_ticket_age_days"] for item in items), "critical_count": sum(1 for item in items if item["aging_band"] == "critical")} for segment, items in sorted(groups.items())]}


def _recommendations(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["Add support ticket aging metadata before exporting escalation aging."]
    if any(row["aging_band"] == "critical" for row in rows):
        return ["Run an executive support review for critical escalations and assign same-day owners."]
    if any(row["aging_band"] == "overdue" for row in rows):
        return ["Prioritize overdue escalations before accepting new support commitments."]
    return ["Maintain escalation aging review and refresh customer update timestamps."]


def _next_action(band: str) -> str:
    return {"critical": "Assign same-day executive owner and customer update.", "overdue": "Clear blocker or reset SLA commitment with customer.", "watchlist": "Confirm next update and owner before SLA breach.", "on_track": "Monitor through normal support review."}[band]


def _metadata(unit: Any) -> dict[str, Any]:
    metadata = getattr(unit, "metadata", None)
    return metadata if isinstance(metadata, dict) else {}


def _number(metadata: dict[str, Any], key: str, default: float) -> float:
    try:
        return float(str(metadata.get(key, default)).replace(",", ""))
    except (TypeError, ValueError):
        return default


def _int(value: float) -> int:
    return max(int(value), 0)


def _items(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.replace(";", ",").split(",") if item.strip()]
    return []


def _md(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")
