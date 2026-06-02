"""Profile signal freshness export report."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Mapping

SCHEMA_VERSION = "max.profile_signal_freshness_report.v1"
KIND = "max.profile_signal_freshness_report"


def build_profile_signal_freshness_report(records: list[Mapping[str, Any]], *, stale_threshold_hours: int = 48, generated_at: str = "2026-06-01T00:00:00+00:00") -> dict[str, Any]:
    rows = []
    now = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    for record in records:
        if not isinstance(record, Mapping):
            continue
        newest = _dt(record.get("newest_signal_at") or record.get("newest_at"))
        oldest_unprocessed = _dt(record.get("oldest_unprocessed_at") or record.get("oldest_pending_at"))
        stale_count = _int(record.get("stale_count"))
        state = "unknown"
        if newest:
            age_hours = (now - newest).total_seconds() / 3600
            state = "stale" if age_hours > stale_threshold_hours or stale_count > 0 else "fresh"
        elif stale_count > 0 or oldest_unprocessed is None:
            state = "stale"
        rows.append({"profile": _text(record.get("profile")) or "unknown-profile", "source": _text(record.get("source")) or "unknown-source", "newest_signal_at": newest.isoformat() if newest else None, "oldest_unprocessed_signal_at": oldest_unprocessed.isoformat() if oldest_unprocessed else None, "stale_threshold_hours": stale_threshold_hours, "stale_count": stale_count, "freshness_state": state, "recommended_fetch_priority": _priority(state, stale_count)})
    rows.sort(key=lambda row: (0 if row["freshness_state"] == "stale" else 1, {"high": 0, "medium": 1, "low": 2}[row["recommended_fetch_priority"]], row["profile"].lower(), row["source"].lower()))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "generated_at": generated_at, "summary": {"row_count": len(rows), "stale_total": sum(1 for row in rows if row["freshness_state"] == "stale")}, "rows": rows}


def render_profile_signal_freshness_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_profile_signal_freshness_report_markdown(report: dict[str, Any]) -> str:
    stale = [row for row in report.get("rows") or [] if row["freshness_state"] == "stale"]
    fresh = [row for row in report.get("rows") or [] if row["freshness_state"] != "stale"]
    lines = ["# Profile Signal Freshness Report", "", "## Stale Sources", ""]
    lines.extend([f"- {row['profile']} / {row['source']}: {row['recommended_fetch_priority']}" for row in stale] or ["- No stale sources."])
    lines.extend(["", "## Fresh Sources", ""])
    lines.extend([f"- {row['profile']} / {row['source']}" for row in fresh] or ["- No fresh sources."])
    return "\n".join(lines).rstrip() + "\n"


def _priority(state: str, stale_count: int) -> str:
    if state == "stale" and stale_count >= 5:
        return "high"
    if state == "stale":
        return "medium"
    return "low"


def _dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
