"""JSON API renderer for publisher webhook latency status."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from max.api._renderer_utils import bool_or_default, float_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.publisher_webhook_latency_status.v1"
KIND = "max.api.publisher_webhook_latency_status"
STATUS_RANK = {"timing_out": 0, "slow": 1, "healthy": 2}


def publisher_webhook_latency_status_to_json(payload: Mapping[str, Any] | Sequence[Mapping[str, Any]], *, slow_p95_ms: float = 1000.0) -> str:
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for item in _items(payload):
        key = (_text(item.get("destination")) or "unknown", _text(item.get("event_type") or item.get("event")) or "unknown")
        group = groups.setdefault(key, {"destination": key[0], "event_type": key[1], "latencies": [], "timeout_count": 0})
        group["latencies"].append(max(0.0, float_or_zero(item.get("latency_ms", item.get("duration_ms")))))
        if bool_or_default(item.get("timeout", item.get("timed_out")), default=False):
            group["timeout_count"] += 1
    rows = [_finish_group(group, slow_p95_ms) for group in groups.values()]
    rows.sort(key=lambda row: (STATUS_RANK[row["status"]], row["destination"], row["event_type"]))
    metadata = source_metadata(payload if isinstance(payload, Mapping) else {}, group_count=len(rows))
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(rows), "webhooks": rows, "metadata": metadata}, indent=2, sort_keys=True)


def _finish_group(group: dict[str, Any], slow_p95_ms: float) -> dict[str, Any]:
    latencies = sorted(group.pop("latencies"))
    p50 = _percentile(latencies, 50)
    p95 = _percentile(latencies, 95)
    status = "timing_out" if group["timeout_count"] else "slow" if p95 > slow_p95_ms else "healthy"
    return {**group, "sample_count": len(latencies), "p50_latency_ms": p50, "p95_latency_ms": p95, "status": status}


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    position = (len(values) - 1) * percentile / 100
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    weight = position - lower
    return round(values[lower] * (1 - weight) + values[upper] * weight, 2)


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"status": "timing_out" if any(row["status"] == "timing_out" for row in rows) else "slow" if any(row["status"] == "slow" for row in rows) else "healthy", "group_count": len(rows), "sample_count": sum(row["sample_count"] for row in rows), "timeout_count": sum(row["timeout_count"] for row in rows)}


def _items(payload: Mapping[str, Any] | Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    if isinstance(payload, Mapping):
        return list_of_maps(payload.get("samples") or payload.get("webhooks") or payload.get("rows") or payload.get("items"))
    return [item for item in payload if isinstance(item, Mapping)]


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
