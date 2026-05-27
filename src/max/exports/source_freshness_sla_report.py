"""Source freshness SLA export report."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Iterable

SCHEMA_VERSION = "max.source_freshness_sla_report.v1"
KIND = "max.source_freshness_sla_report"
DEFAULT_GENERATED_AT = "2026-05-27T00:00:00+00:00"


def build_source_freshness_sla_report(records: Iterable[dict[str, Any]], *, now: str = DEFAULT_GENERATED_AT, warning_ratio: float = 0.8, title: str = "Source Freshness SLA Report", generated_at: str = DEFAULT_GENERATED_AT) -> dict[str, Any]:
    current = _parse(now)
    rows = [_row(raw, current, warning_ratio) for raw in records if isinstance(raw, dict)]
    rows.sort(key=lambda r: ({"breached": 0, "warning": 1, "healthy": 2}[r["breach_status"]], -r["current_age_minutes"], r["source"].lower()))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "generated_at": _text(generated_at) or DEFAULT_GENERATED_AT, "title": _text(title) or "Source Freshness SLA Report", "summary": {"source_count": len(rows), "breached_count": sum(1 for r in rows if r["breach_status"] == "breached"), "warning_count": sum(1 for r in rows if r["breach_status"] == "warning"), "healthy_count": sum(1 for r in rows if r["breach_status"] == "healthy")}, "freshness_rows": rows}


def render_source_freshness_sla_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_source_freshness_sla_report_markdown(report: dict[str, Any]) -> str:
    lines = [f"# {report.get('title') or 'Source Freshness SLA Report'}", "", "## Freshness", ""]
    lines.extend([f"- {r['source']} {r['breach_status']}: {r['current_age_minutes']}m" for r in report.get("freshness_rows") or []] or ["- No source freshness rows."])
    return "\n".join(lines).rstrip() + "\n"


def _row(raw: dict[str, Any], current: datetime, warning_ratio: float) -> dict[str, Any]:
    source = _text(raw.get("source")) or "unknown-source"
    last = _text(raw.get("last_successful_fetch_at") or raw.get("last_success_at"))
    max_age = _int(raw.get("max_age_minutes", raw.get("sla_minutes", 60)))
    age = round((current - _parse(last)).total_seconds() / 60) if last else 10**9
    status = "breached" if not last or age > max_age else "warning" if age >= max_age * warning_ratio else "healthy"
    reason = "missing last successful fetch timestamp" if not last else "freshness SLA breached" if status == "breached" else "approaching freshness SLA" if status == "warning" else "within freshness SLA"
    return {"source": source, "profile": _text(raw.get("profile")) or "default", "last_successful_fetch_at": last, "max_age_minutes": max_age, "current_age_minutes": age, "breach_status": status, "reason": reason, "escalation_recommendation": "page source owner and run recovery fetch" if status == "breached" else "watch next fetch window" if status == "warning" else "no escalation"}


def _parse(value: str) -> datetime:
    if not value:
        return datetime.fromtimestamp(0, timezone.utc)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
