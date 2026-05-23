"""Insight confidence decay export report."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.insight_confidence_decay_report.v1"
KIND = "max.insight_confidence_decay_report"

_ORDER = {"refresh now": 0, "review soon": 1, "monitor": 2}


def build_insight_confidence_decay_report_export(store: Store, domain: str | None = None) -> dict[str, Any]:
    today = datetime.now(timezone.utc).date()
    rows = [_row(unit, today) for unit in store.get_buildable_units(limit=1000, domain=domain)]
    rows.sort(key=lambda row: (_ORDER[row["refresh_recommendation"]], -row["decay_points"], row["owner"].lower(), row["title"].lower()))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {"project": "max", "entity_type": "insight_confidence_decay_report", "domain_filter": domain},
        "summary": _summary(rows),
        "insight_rows": rows,
        "refresh_queue": [row for row in rows if row["refresh_recommendation"] != "monitor"],
    }


def render_insight_confidence_decay_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str)


def render_insight_confidence_decay_report_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        "# Insight Confidence Decay Report",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Generated: {report['generated_at']}",
        "",
        "## Summary",
        "",
        f"- Insights analyzed: {summary.get('insight_count', 0)}",
        f"- Decayed insights: {summary.get('decayed_insight_count', 0)}",
        f"- Average decay points: {summary.get('average_decay_points', 0)}",
        "",
        "## Refresh Queue",
        "",
    ]
    queue = report.get("refresh_queue") or []
    if queue:
        lines.extend(["| Insight | Owner | Confidence | Decay | Last Evidence | Recommendation |", "|---------|-------|------------|-------|---------------|----------------|"])
        for row in queue:
            lines.append(f"| {_md(row['title'])} | {_md(row['owner'])} | {row['current_confidence']} | {row['decay_points']} | {row['last_evidence_at'] or ''} | {row['refresh_recommendation']} |")
    else:
        lines.append("- No insights need refresh.")
    stable = [row for row in report.get("insight_rows", []) if row["refresh_recommendation"] == "monitor"]
    lines.extend(["", "## Stable Insights", ""])
    if stable:
        for row in stable:
            lines.append(f"- {row['insight_id']}: {row['current_confidence']} confidence, {row['decay_points']} decay points")
    else:
        lines.append("- No stable insights.")
    return "\n".join(lines).rstrip() + "\n"


def _row(unit: Any, today: date) -> dict[str, Any]:
    metadata = _metadata(unit)
    original = _confidence(metadata.get("original_confidence") or metadata.get("initial_confidence") or metadata.get("confidence"))
    current = _confidence(metadata.get("current_confidence") or metadata.get("latest_confidence") or metadata.get("confidence"))
    explicit_decay = _number(metadata.get("decay_points") or metadata.get("confidence_decay_points"))
    decay = _clamp(int(round(explicit_decay)), 0, 100) if explicit_decay is not None else max(0, original - current)
    last_evidence = _parse_date(metadata.get("last_evidence_at") or metadata.get("evidence_timestamp") or metadata.get("last_supported_at"))
    days_without_support = _nonnegative_int(metadata.get("days_without_support"))
    if days_without_support is None:
        days_without_support = max(0, (today - last_evidence).days) if last_evidence else 0
    return {
        "insight_id": _text(metadata.get("insight_id") or getattr(unit, "id", "")) or "unknown-insight",
        "title": _text(metadata.get("title") or getattr(unit, "title", "")) or "Untitled insight",
        "original_confidence": original,
        "current_confidence": current,
        "decay_points": decay,
        "last_evidence_at": last_evidence.isoformat() if last_evidence else "",
        "days_without_support": days_without_support,
        "owner": _text(metadata.get("owner")) or "Unassigned",
        "refresh_recommendation": _recommendation(decay, days_without_support),
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    decayed = [row for row in rows if row["decay_points"] > 0]
    return {
        "insight_count": len(rows),
        "decayed_insight_count": len(decayed),
        "average_decay_points": round(sum(row["decay_points"] for row in rows) / len(rows), 2) if rows else 0.0,
        "refresh_needed_count": sum(1 for row in rows if row["refresh_recommendation"] != "monitor"),
    }


def _recommendation(decay: int, days_without_support: int) -> str:
    if decay >= 25 or days_without_support >= 90:
        return "refresh now"
    if decay >= 10 or days_without_support >= 45:
        return "review soon"
    return "monitor"


def _metadata(unit: Any) -> dict[str, Any]:
    metadata = getattr(unit, "metadata", None)
    return metadata if isinstance(metadata, dict) else {}


def _confidence(value: Any) -> int:
    number = _number(value)
    return _clamp(int(round(number if number is not None else 0)), 0, 100)


def _nonnegative_int(value: Any) -> int | None:
    number = _number(value)
    return max(0, int(round(number))) if number is not None else None


def _number(value: Any) -> float | None:
    try:
        return float(str(value).replace("%", "").strip())
    except (TypeError, ValueError):
        return None


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def _parse_date(value: Any) -> date | None:
    text = _text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""


def _md(value: Any) -> str:
    return str(value).replace("|", "\\|")
