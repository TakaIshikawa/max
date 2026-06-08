"""JSON API renderer for adapter fetch latency status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import float_or_zero, int_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.adapter_fetch_latency_status.v1"
KIND = "max.api.adapter_fetch_latency_status"
STATUS_RANK = {"critical": 0, "degraded": 1, "healthy": 2, "idle": 3}


def adapter_fetch_latency_status_to_json(payload: Mapping[str, Any], *, p95_threshold_ms: float = 1000, p99_threshold_ms: float = 2000) -> str:
    rows = [_row(item, index, p95_threshold_ms, p99_threshold_ms) for index, item in enumerate(list_of_maps(payload.get("adapters") or payload.get("rows") or payload.get("items")), start=1)]
    rows.sort(key=lambda row: (STATUS_RANK[row["status"]], row["adapter"], row["source"]))
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(rows), "adapters": rows, "metadata": source_metadata(payload, adapter_count=len(rows))}, indent=2, sort_keys=True)


def _row(item: Mapping[str, Any], index: int, p95_threshold: float, p99_threshold: float) -> dict[str, Any]:
    sample_count = max(0, int_or_zero(item.get("sample_count", item.get("samples"))))
    p50 = _latency(item, "p50")
    p95 = _latency(item, "p95")
    p99 = _latency(item, "p99")
    breaches = []
    if sample_count and p95 > p95_threshold:
        breaches.append("p95")
    if sample_count and p99 > p99_threshold:
        breaches.append("p99")
    status = "idle" if sample_count == 0 else "critical" if "p99" in breaches else "degraded" if breaches else "healthy"
    return {"adapter": _text(item.get("adapter") or item.get("adapter_id")) or f"adapter-{index}", "source": _text(item.get("source") or item.get("source_id")) or "unknown", "p50_ms": p50, "p95_ms": p95, "p99_ms": p99, "sample_count": sample_count, "threshold_breaches": breaches, "status": status}


def _latency(item: Mapping[str, Any], name: str) -> float:
    return round(max(0.0, float_or_zero(item.get(f"{name}_ms", item.get(name)))), 2)


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"status": "critical" if any(row["status"] == "critical" for row in rows) else "degraded" if any(row["status"] == "degraded" for row in rows) else "healthy" if rows else "idle", "adapter_count": len(rows), "breached_adapter_count": sum(1 for row in rows if row["threshold_breaches"]), "idle_adapter_count": sum(1 for row in rows if row["status"] == "idle")}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
