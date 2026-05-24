"""JSON API renderer for adaptive source fetch allocation status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "max.api.source_fetch_allocation_status.v1"
KIND = "max.api.source_fetch_allocation_status"


def source_fetch_allocation_status_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    sources = _sources(payload)
    drift_threshold = _ratio(payload.get("drift_threshold", payload.get("threshold", 0.1)), 0.1)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(sources, drift_threshold),
        "sources": sources,
        "underallocated_sources": [row for row in sources if row["drift_from_target"] < -drift_threshold and not row["suppressed"]],
        "overallocated_sources": [row for row in sources if row["drift_from_target"] > drift_threshold],
        "suppressed_sources": [row for row in sources if row["suppressed"]],
        "next_adjustment_recommendations": _recommendations(sources, drift_threshold),
        "metadata": _metadata(payload, sources, as_of),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _sources(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("sources") if isinstance(payload.get("sources"), list) else payload.get("allocations")
    items = [item for item in source if isinstance(item, Mapping)] if isinstance(source, list) else []
    requested_total = sum(_count(item.get("requested", item.get("requested_fetches"))) for item in items)
    actual_total = sum(_count(item.get("actual", item.get("actual_fetches", item.get("fetched")))) for item in items)
    rows = [_source(item, index, requested_total, actual_total) for index, item in enumerate(items, start=1)]
    rows.sort(key=lambda row: (-abs(row["drift_from_target"]), row["source"]))
    return rows


def _source(item: Mapping[str, Any], index: int, requested_total: int, actual_total: int) -> dict[str, Any]:
    requested = _count(item.get("requested", item.get("requested_fetches")))
    actual = _count(item.get("actual", item.get("actual_fetches", item.get("fetched"))))
    target = _ratio(item.get("target_share", item.get("target")), 0.0)
    if not target and requested_total:
        target = round(requested / requested_total, 4)
    actual_share = round(actual / actual_total, 4) if actual_total else 0.0
    suppressed = _bool(item.get("suppressed", item.get("circuit_breaker_open", item.get("circuit_breaker"))))
    return {
        "source": _text(item.get("source") or item.get("name")) or f"source-{index}",
        "requested_count": requested,
        "actual_count": actual,
        "requested_share": round(requested / requested_total, 4) if requested_total else 0.0,
        "actual_share": actual_share,
        "target_share": target,
        "drift_from_target": round(actual_share - target, 4),
        "suppressed": suppressed,
        "suppression_reason": _text(item.get("suppression_reason") or item.get("reason")),
    }


def _recommendations(sources: list[dict[str, Any]], drift_threshold: float) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in sources:
        if row["suppressed"]:
            rows.append({"source": row["source"], "action": "Resolve circuit breaker suppression before allocating more fetches", "reason": row["suppression_reason"]})
        elif row["drift_from_target"] < -drift_threshold:
            rows.append({"source": row["source"], "action": "Increase next fetch allocation", "drift_from_target": row["drift_from_target"]})
        elif row["drift_from_target"] > drift_threshold:
            rows.append({"source": row["source"], "action": "Reduce next fetch allocation", "drift_from_target": row["drift_from_target"]})
    return rows


def _summary(sources: list[dict[str, Any]], drift_threshold: float) -> dict[str, Any]:
    return {
        "source_count": len(sources),
        "drift_threshold": drift_threshold,
        "requested_count": sum(row["requested_count"] for row in sources),
        "actual_count": sum(row["actual_count"] for row in sources),
        "suppressed_count": sum(1 for row in sources if row["suppressed"]),
    }


def _metadata(payload: Mapping[str, Any], sources: list[dict[str, Any]], as_of: str | datetime | None) -> dict[str, Any]:
    metadata = dict(payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {})
    return {**metadata, "source_schema_version": payload.get("schema_version"), "source_kind": payload.get("kind"), "as_of": _as_of(as_of), "source_count": len(sources)}


def _ratio(value: Any, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number > 1:
        number = number / 100
    return round(min(max(number, 0.0), 1.0), 4)


def _count(value: Any) -> int:
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def _bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "open"}
    return bool(value)


def _as_of(value: str | datetime | None) -> str | None:
    if isinstance(value, datetime):
        parsed = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return value


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
