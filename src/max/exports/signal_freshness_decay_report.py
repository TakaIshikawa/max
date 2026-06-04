"""Signal freshness decay export report."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable

SCHEMA_VERSION = "max.signal_freshness_decay_report.v1"
KIND = "max.signal_freshness_decay_report"
DEFAULT_NOW = "2026-06-05T00:00:00+00:00"
RISK_RANK = {"high": 0, "medium": 1, "low": 2}


def generate_signal_freshness_decay_report(records: Iterable[dict[str, Any]], now: str | datetime | None = None) -> dict[str, Any]:
    as_of = _dt(now) or _dt(DEFAULT_NOW)
    groups: dict[str, dict[str, Any]] = defaultdict(lambda: {"fresh": 0, "aging": 0, "stale": 0, "malformed": 0, "oldest": None})
    for raw in records:
        source = _text(raw.get("source") or raw.get("source_id") or raw.get("adapter")) or "unknown-source"
        seen = _dt(raw.get("seen_at") or raw.get("observed_at") or raw.get("timestamp") or raw.get("created_at"))
        group = groups[source]
        if seen is None:
            group["malformed"] += 1
            continue
        age_hours = max(0.0, (as_of - seen).total_seconds() / 3600)
        bucket = "fresh" if age_hours <= 24 else "aging" if age_hours <= 168 else "stale"
        group[bucket] += 1
        group["oldest"] = seen if group["oldest"] is None or seen < group["oldest"] else group["oldest"]

    rows = []
    for source, group in groups.items():
        count = group["fresh"] + group["aging"] + group["stale"] + group["malformed"]
        stale_ratio = _ratio(group["stale"] + group["malformed"], count)
        rows.append(
            {
                "source": source,
                "signal_count": count,
                "fresh_count": group["fresh"],
                "aging_count": group["aging"],
                "stale_count": group["stale"],
                "malformed_timestamp_count": group["malformed"],
                "stale_ratio": stale_ratio,
                "oldest_seen_at": group["oldest"].isoformat() if group["oldest"] else None,
                "freshness_risk": _risk(stale_ratio),
            }
        )
    rows.sort(key=lambda row: (-row["stale_ratio"], row["source"].lower()))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": as_of.isoformat(),
        "summary": {
            "source_count": len(rows),
            "signal_count": sum(row["signal_count"] for row in rows),
            "stale_signal_count": sum(row["stale_count"] for row in rows),
            "malformed_timestamp_count": sum(row["malformed_timestamp_count"] for row in rows),
            "freshness_risk": _risk(max((row["stale_ratio"] for row in rows), default=0.0)),
        },
        "rows": rows,
    }


def render_signal_freshness_decay_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_signal_freshness_decay_report_markdown(report: dict[str, Any]) -> str:
    lines = ["# Signal Freshness Decay Report", "", "## Sources", ""]
    rows = report.get("rows") or []
    lines.extend([f"- {row['source']}: {row['stale_ratio']} stale ({row['freshness_risk']})" for row in rows] or ["- No signals supplied."])
    return "\n".join(lines).rstrip() + "\n"


def _risk(stale_ratio: float) -> str:
    if stale_ratio >= 0.5:
        return "high"
    if stale_ratio >= 0.25:
        return "medium"
    return "low"


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


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
