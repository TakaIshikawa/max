"""Publication channel effectiveness export report."""

from __future__ import annotations

import json
from typing import Any, Iterable

SCHEMA_VERSION = "max.publication_channel_effectiveness_report.v1"
KIND = "max.publication_channel_effectiveness_report"
DEFAULT_GENERATED_AT = "2026-05-27T00:00:00+00:00"


def build_publication_channel_effectiveness_report(records: Iterable[dict[str, Any]], *, title: str = "Publication Channel Effectiveness Report", generated_at: str = DEFAULT_GENERATED_AT, minimum_success_rate: float = 0.9, maximum_delivery_minutes: float = 30.0) -> dict[str, Any]:
    rows = []
    for raw in records:
        attempted = _int(raw.get("attempted_count"))
        successful = min(_int(raw.get("successful_count")), attempted) if attempted else _int(raw.get("successful_count"))
        failed = _int(raw.get("failed_count")) or max(attempted - successful, 0)
        avg = _float(raw.get("average_delivery_minutes"))
        rate = round(successful / attempted, 4) if attempted else 0.0
        weak = rate < minimum_success_rate or avg > maximum_delivery_minutes
        rows.append({"destination": _text(raw.get("destination")) or "unknown-destination", "channel": _text(raw.get("channel")) or "unknown-channel", "profile": _text(raw.get("profile")) or "unknown-profile", "attempted_count": attempted, "successful_count": successful, "failed_count": failed, "success_rate": rate, "average_delivery_minutes": round(avg, 2), "effectiveness_status": "weak" if weak else "healthy"})
    rows.sort(key=lambda row: (row["effectiveness_status"] != "weak", row["destination"].lower(), row["channel"].lower(), row["profile"].lower()))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "generated_at": _text(generated_at) or DEFAULT_GENERATED_AT, "title": _text(title) or "Publication Channel Effectiveness Report", "summary": {"attempted_count": sum(row["attempted_count"] for row in rows), "successful_count": sum(row["successful_count"] for row in rows), "weak_channel_count": sum(1 for row in rows if row["effectiveness_status"] == "weak")}, "channel_effectiveness": rows, "weak_channels": [row for row in rows if row["effectiveness_status"] == "weak"]}


def render_publication_channel_effectiveness_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_publication_channel_effectiveness_report_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    return "\n".join([f"# {report.get('title') or 'Publication Channel Effectiveness Report'}", "", "## Summary", "", f"- Attempted: {summary.get('attempted_count', 0)}", f"- Successful: {summary.get('successful_count', 0)}", f"- Weak channels: {summary.get('weak_channel_count', 0)}"]).rstrip() + "\n"


def _float(value: Any) -> float:
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return 0.0


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
