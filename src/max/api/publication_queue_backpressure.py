"""JSON API renderer for publication queue backpressure."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "max.api.publication_queue_backpressure.v1"
KIND = "max.api.publication_queue_backpressure"
STATUS_RANK = {"blocked": 0, "backlogged": 1, "normal": 2}


def publication_queue_backpressure_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    destinations = _destinations(payload)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(destinations),
        "destinations": destinations,
        "blocked_destinations": [row for row in destinations if row["status"] == "blocked"],
        "metadata": _metadata(payload, destinations, as_of),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _destinations(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("destinations") if isinstance(payload.get("destinations"), list) else payload.get("publication_destinations")
    rows = [_destination(item, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    rows.sort(key=lambda row: (STATUS_RANK[row["status"]], row["destination"]))
    return rows


def _destination(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    pending = _int(item.get("pending_count", item.get("pending")))
    inflight = _int(item.get("inflight_count", item.get("inflight")))
    failed = _int(item.get("failed_count", item.get("failed")))
    age = _int(item.get("oldest_pending_age_minutes", item.get("oldest_age_minutes")))
    rate_limited = _bool(item.get("rate_limited"))
    status = "blocked" if rate_limited or failed >= 5 else ("backlogged" if pending >= 50 or age >= 60 else "normal")
    return {
        "destination": _text(item.get("destination") or item.get("name")) or f"destination-{index}",
        "pending_count": pending,
        "inflight_count": inflight,
        "failed_count": failed,
        "oldest_pending_age_minutes": age,
        "rate_limited": rate_limited,
        "retry_after_seconds": _int(item.get("retry_after_seconds", item.get("retry_after"))),
        "status": status,
    }


def _summary(destinations: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row["status"] for row in destinations)
    return {
        "destination_count": len(destinations),
        "pending_count": sum(row["pending_count"] for row in destinations),
        "inflight_count": sum(row["inflight_count"] for row in destinations),
        "failed_count": sum(row["failed_count"] for row in destinations),
        "backlogged_count": counts["backlogged"],
        "blocked_count": counts["blocked"],
    }


def _metadata(payload: Mapping[str, Any], destinations: list[dict[str, Any]], as_of: str | datetime | None) -> dict[str, Any]:
    metadata = dict(payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {})
    return {**metadata, "source_schema_version": payload.get("schema_version"), "source_kind": payload.get("kind"), "as_of": _as_of(as_of), "destination_count": len(destinations)}


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def _bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _as_of(value: str | datetime | None) -> str | None:
    if isinstance(value, datetime):
        parsed = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return value


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
