"""JSON API renderer for source priority rebalance status."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from max.api._renderer_utils import datetime_to_string, float_or_zero, int_or_zero, source_metadata

SCHEMA_VERSION = "max.api.source_priority_rebalance_status.v1"
KIND = "max.api.source_priority_rebalance_status"
STATUS_RANK = {"increase": 0, "decrease": 1, "hold": 2}


def source_priority_rebalance_status_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    sources = _sources(payload)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(sources),
        "sources": sources,
        "top_rebalance_actions": sources[: max(0, int_or_zero(payload.get("limit", payload.get("top_n", 10))))],
        "metadata": source_metadata(payload, as_of=datetime_to_string(as_of) if isinstance(as_of, datetime) else as_of, source_count=len(sources)),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _sources(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("sources") if isinstance(payload.get("sources"), list) else payload.get("allocations")
    if not isinstance(source, list):
        source = payload.get("items")
    rows = [_source(item, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    return sorted(rows, key=lambda row: (-abs(row["delta_share"]), STATUS_RANK[row["action"]], row["source"]))


def _source(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    current = _ratio(item.get("current_fetch_share", item.get("current_share", item.get("share", item.get("current_percentage")))))
    recommended = _ratio(item.get("recommended_fetch_share", item.get("recommended_share", item.get("target_share", item.get("recommended_percentage")))))
    delta = round(recommended - current, 4)
    threshold = _ratio(item.get("rebalance_threshold", item.get("threshold", 0.025)))
    if delta > threshold:
        action = "increase"
    elif delta < -threshold:
        action = "decrease"
    else:
        action = "hold"
    return {
        "source": _text(item.get("source") or item.get("source_id") or item.get("id")) or f"source-{index}",
        "profile": _bucket(item.get("profile"), "default"),
        "current_fetch_share": current,
        "recommended_fetch_share": recommended,
        "delta_share": delta,
        "delta_percentage_points": round(delta * 100, 2),
        "priority": max(0, int_or_zero(item.get("priority", item.get("rank")))),
        "action": action,
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row["action"] for row in rows)
    status = "rebalance_required" if counts["increase"] or counts["decrease"] else "balanced"
    return {"status": status, "source_count": len(rows), "increase_count": counts["increase"], "decrease_count": counts["decrease"], "hold_count": counts["hold"]}


def _ratio(value: Any) -> float:
    return round(min(max(float_or_zero(value), 0.0), 1.0), 4)


def _bucket(value: Any, default: str) -> str:
    return (_text(value) or default).lower().replace(" ", "_")


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
