"""JSON API renderer for insight freshness windows."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "max.api.insight_freshness_window.v1"
KIND = "max.api.insight_freshness_window"
STATUS_RANK = {"expired": 0, "stale": 1, "fresh": 2}


def insight_freshness_window_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    insights = _insights(payload)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(insights),
        "insights": insights,
        "profile_totals": _totals(insights, "profile"),
        "category_totals": _totals(insights, "category"),
        "refresh_needed": [row for row in insights if row["status"] in {"stale", "expired"}],
        "metadata": _metadata(payload, insights, as_of),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _insights(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("insights") if isinstance(payload.get("insights"), list) else payload.get("freshness_windows")
    rows = [_insight(item, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    rows.sort(key=lambda row: (STATUS_RANK[row["status"]], row["profile"], row["category"], row["insight_id"]))
    return rows


def _insight(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    freshness = _int(item.get("freshness_days", item.get("age_days")))
    window = _int(item.get("window_days", item.get("freshness_window_days", 30))) or 30
    status = "expired" if freshness >= window * 2 else ("stale" if freshness > window else "fresh")
    return {
        "insight_id": _text(item.get("insight_id") or item.get("id")) or f"insight-{index}",
        "profile": _text(item.get("profile")) or "unknown-profile",
        "category": _text(item.get("category")) or "uncategorized",
        "last_signal_at": item.get("last_signal_at"),
        "last_synthesized_at": item.get("last_synthesized_at") or item.get("synthesized_at"),
        "freshness_days": freshness,
        "window_days": window,
        "confidence": _score(item.get("confidence", item.get("confidence_score"))),
        "status": status,
    }


def _summary(insights: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row["status"] for row in insights)
    return {"insight_count": len(insights), "stale_count": counts["stale"], "expired_count": counts["expired"], "refresh_needed_count": counts["stale"] + counts["expired"]}


def _totals(insights: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in insights:
        grouped[row[field]].append(row)
    rows = [{field: key, "insight_count": len(items), "stale_count": sum(1 for item in items if item["status"] == "stale"), "expired_count": sum(1 for item in items if item["status"] == "expired")} for key, items in grouped.items()]
    rows.sort(key=lambda row: (-(row["stale_count"] + row["expired_count"]), row[field]))
    return rows


def _metadata(payload: Mapping[str, Any], insights: list[dict[str, Any]], as_of: str | datetime | None) -> dict[str, Any]:
    metadata = dict(payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {})
    return {**metadata, "source_schema_version": payload.get("schema_version"), "source_kind": payload.get("kind"), "as_of": _as_of(as_of), "insight_count": len(insights)}


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def _score(value: Any) -> float:
    try:
        return round(min(max(float(value or 0), 0.0), 1.0), 4)
    except (TypeError, ValueError):
        return 0.0


def _as_of(value: str | datetime | None) -> str | None:
    if isinstance(value, datetime):
        parsed = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return value


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
