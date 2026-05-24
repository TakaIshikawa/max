"""JSON API renderer for adapter rate limit status."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "max.api.adapter_rate_limit_status.v1"
KIND = "max.api.adapter_rate_limit_status"
STATUS_RANK = {"exhausted": 0, "throttled": 1, "near_limit": 2, "healthy": 3}


def adapter_rate_limit_status_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    adapters = _adapters(payload)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(adapters),
        "adapters": adapters,
        "adapter_totals": _totals(adapters, "adapter"),
        "source_totals": _totals(adapters, "source"),
        "throttled_adapters": [row for row in adapters if row["status"] in {"throttled", "exhausted"}],
        "metadata": _metadata(payload, adapters, as_of),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _adapters(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("adapters") if isinstance(payload.get("adapters"), list) else payload.get("rate_limits")
    rows = [_adapter(item, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    rows.sort(key=lambda row: (STATUS_RANK[row["status"]], row["adapter"], row["source"]))
    return rows


def _adapter(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    limit = _int(item.get("limit", item.get("limit_count")))
    remaining = min(_int(item.get("remaining", item.get("remaining_count"))), limit) if limit else _int(item.get("remaining", item.get("remaining_count")))
    ratio = round(remaining / limit, 4) if limit else 0.0
    throttled = _bool(item.get("throttled"))
    status = "exhausted" if limit and remaining <= 0 else ("throttled" if throttled else ("near_limit" if limit and ratio <= 0.1 else "healthy"))
    return {
        "adapter": _text(item.get("adapter") or item.get("adapter_name")) or f"adapter-{index}",
        "source": _text(item.get("source") or item.get("source_name")) or "unknown-source",
        "limit": limit,
        "remaining": remaining,
        "remaining_ratio": ratio,
        "reset_after_seconds": _int(item.get("reset_after_seconds", item.get("reset_after"))),
        "window_seconds": _int(item.get("window_seconds", item.get("window"))),
        "throttled": throttled,
        "request_count": _int(item.get("request_count", item.get("requests"))),
        "status": status,
    }


def _summary(adapters: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row["status"] for row in adapters)
    return {"adapter_count": len(adapters), "exhausted_count": counts["exhausted"], "throttled_count": counts["throttled"], "near_limit_count": counts["near_limit"], "total_remaining": sum(row["remaining"] for row in adapters)}


def _totals(adapters: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in adapters:
        grouped[row[field]].append(row)
    return [{field: key, "adapter_count": len(items), "total_remaining": sum(item["remaining"] for item in items), "throttled_count": sum(1 for item in items if item["status"] in {"throttled", "exhausted"})} for key, items in sorted(grouped.items())]


def _metadata(payload: Mapping[str, Any], adapters: list[dict[str, Any]], as_of: str | datetime | None) -> dict[str, Any]:
    metadata = dict(payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {})
    return {**metadata, "source_schema_version": payload.get("schema_version"), "source_kind": payload.get("kind"), "as_of": _as_of(as_of), "adapter_count": len(adapters)}


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
