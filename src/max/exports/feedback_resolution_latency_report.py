"""Feedback resolution latency export report."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable

SCHEMA_VERSION = "max.feedback_resolution_latency_report.v1"
KIND = "max.feedback_resolution_latency_report"
DEFAULT_NOW = "2026-06-05T00:00:00+00:00"
SLA_HOURS = 72
RISK_RANK = {"high": 0, "medium": 1, "low": 2}


def generate_feedback_resolution_latency_report(records: Iterable[dict[str, Any]], now: str | datetime | None = None) -> dict[str, Any]:
    as_of = _dt(now) or _dt(DEFAULT_NOW)
    groups: dict[str, dict[str, Any]] = defaultdict(lambda: {"items": 0, "resolved": 0, "resolved_hours": 0.0, "unresolved": 0, "breaches": 0})
    for raw in records:
        key = _text(raw.get("reviewer_id") or raw.get("reviewer") or raw.get("queue")) or "unknown-queue"
        created = _dt(raw.get("created_at") or raw.get("submitted_at") or raw.get("timestamp"))
        resolved = _dt(raw.get("resolved_at") or raw.get("closed_at"))
        group = groups[key]
        group["items"] += 1
        if created and resolved:
            group["resolved"] += 1
            group["resolved_hours"] += max(0.0, (resolved - created).total_seconds() / 3600)
        else:
            group["unresolved"] += 1
            age_hours = max(0.0, (as_of - created).total_seconds() / 3600) if created else SLA_HOURS + 1
            if age_hours > SLA_HOURS:
                group["breaches"] += 1
    rows = []
    for owner, group in groups.items():
        avg = round(group["resolved_hours"] / group["resolved"], 2) if group["resolved"] else 0.0
        risk = _risk(avg, group["breaches"])
        rows.append({"reviewer_or_queue": owner, "feedback_count": group["items"], "resolved_count": group["resolved"], "average_resolved_latency_hours": avg, "unresolved_count": group["unresolved"], "unresolved_sla_breach_count": group["breaches"], "latency_risk": risk})
    rows.sort(key=lambda row: (RISK_RANK[row["latency_risk"]], -row["unresolved_sla_breach_count"], -row["average_resolved_latency_hours"], row["reviewer_or_queue"].lower()))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "generated_at": as_of.isoformat(), "summary": {"group_count": len(rows), "feedback_count": sum(r["feedback_count"] for r in rows), "unresolved_sla_breach_count": sum(r["unresolved_sla_breach_count"] for r in rows), "high_risk_count": sum(1 for r in rows if r["latency_risk"] == "high")}, "rows": rows}


def _risk(avg_resolved_hours: float, breaches: int) -> str:
    if breaches >= 2 or avg_resolved_hours > SLA_HOURS * 2:
        return "high"
    if breaches or avg_resolved_hours > SLA_HOURS:
        return "medium"
    return "low"


def _dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
