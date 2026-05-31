"""Source freshness gap export report."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Iterable

SCHEMA_VERSION = "max.source_freshness_gap_report.v1"
KIND = "max.source_freshness_gap_report"
DEFAULT_GENERATED_AT = "2026-05-31T00:00:00+00:00"
SEVERITY_RANK = {"critical": 0, "warn": 1, "ok": 2}


def generate_source_freshness_gap_report(records: Iterable[dict[str, Any]], *, now: str = DEFAULT_GENERATED_AT, source_freshness_sla_hours: float = 24.0, generated_at: str = DEFAULT_GENERATED_AT) -> dict[str, Any]:
    current = _parse(now)
    rows = [_row(item, index, current, source_freshness_sla_hours) for index, item in enumerate(records, start=1)]
    rows.sort(key=lambda row: (SEVERITY_RANK[row["severity"]], row["source"], row["profile"], row["category"]))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "generated_at": generated_at, "summary": {"source_count": len(rows), "breached_count": sum(1 for row in rows if row["breach_status"] != "ok"), "no_successful_fetch_count": sum(1 for row in rows if row["breach_status"] == "no-successful-fetch"), "stale_fetch_count": sum(1 for row in rows if row["breach_status"] == "stale-fetch"), "stale_signal_count": sum(1 for row in rows if row["breach_status"] == "stale-signal")}, "rows": rows}


def render_source_freshness_gap_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_source_freshness_gap_report_markdown(report: dict[str, Any]) -> str:
    lines = ["# Source Freshness Gap Report", "", f"Breached sources: {report.get('summary', {}).get('breached_count', 0)}", ""]
    for row in report.get("rows") or []:
        lines.append(f"- {row['source']} / {row['profile']} / {row['category']}: fetch {row['last_successful_fetch_age_hours']}h, signal {row['newest_signal_age_hours']}h ({row['breach_status']})")
    return "\n".join(lines).rstrip() + "\n"


def _row(item: dict[str, Any], index: int, now: datetime, sla_hours: float) -> dict[str, Any]:
    last_fetch = _text(item.get("last_successful_fetch_at") or item.get("last_success_at"))
    newest_signal = _text(item.get("newest_signal_at") or item.get("latest_signal_at") or item.get("signal_at"))
    fetch_age = _age_hours(last_fetch, now)
    signal_age = _age_hours(newest_signal, now)
    status = "ok"
    if not last_fetch:
        status = "no-successful-fetch"
    elif fetch_age > sla_hours:
        status = "stale-fetch"
    elif not newest_signal or signal_age > sla_hours:
        status = "stale-signal"
    severity = "critical" if status == "no-successful-fetch" else ("warn" if status != "ok" else "ok")
    return {"source": _text(item.get("source")) or f"source-{index}", "profile": _text(item.get("profile")) or "default", "category": _text(item.get("category")) or "uncategorized", "last_successful_fetch_at": last_fetch, "newest_signal_at": newest_signal, "source_freshness_sla_hours": round(float(sla_hours), 2), "last_successful_fetch_age_hours": fetch_age, "newest_signal_age_hours": signal_age, "breach_status": status, "severity": severity, "recommended_action": "Run first successful fetch and validate credentials." if status == "no-successful-fetch" else ("Recover fetch cadence." if status == "stale-fetch" else ("Inspect adapter normalization and signal timestamps." if status == "stale-signal" else "No action required."))}


def _age_hours(value: str, now: datetime) -> float:
    return round(max(0.0, (now - _parse(value)).total_seconds() / 3600), 2) if value else 0.0


def _parse(value: str) -> datetime:
    if not value:
        return datetime.fromtimestamp(0, timezone.utc)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
