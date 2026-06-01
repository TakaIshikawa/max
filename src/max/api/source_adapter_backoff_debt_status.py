"""JSON API renderer for source adapter backoff debt status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.source_adapter_backoff_debt_status.v1"
KIND = "max.api.source_adapter_backoff_debt_status"


def source_adapter_backoff_debt_status_to_json(payload: Mapping[str, Any]) -> str:
    threshold = int_or_zero(payload.get("max_delay_threshold_seconds", payload.get("critical_delay_seconds", 300)))
    rows = [_row(item, index, threshold) for index, item in enumerate(list_of_maps(payload.get("adapters") or payload.get("backoffs") or payload.get("rows")), start=1)]
    rows = [row for row in rows if row["delayed_fetches"] > 0 or row["remaining_delay_seconds"] > 0]
    rows.sort(key=lambda row: (row["status"] != "critical", -row["remaining_delay_seconds"], -row["delayed_fetches"], row["adapter"]))
    status = "critical" if any(row["status"] == "critical" for row in rows) else ("warning" if rows else "healthy")
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"status": status, "delayed_adapter_count": len(rows), "total_delayed_fetches": sum(row["delayed_fetches"] for row in rows), "max_remaining_delay_seconds": max((row["remaining_delay_seconds"] for row in rows), default=0), "max_delay_threshold_seconds": threshold}, "adapters": rows, "metadata": source_metadata(payload)}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _row(item: Mapping[str, Any], index: int, threshold: int) -> dict[str, Any]:
    remaining = max(0, int_or_zero(item.get("remaining_delay_seconds", item.get("delay_seconds"))))
    delayed = max(0, int_or_zero(item.get("delayed_fetches", item.get("fetches"))))
    return {"adapter": str(item.get("adapter") or item.get("name") or item.get("id") or f"adapter-{index}"), "delayed_fetches": delayed, "remaining_delay_seconds": remaining, "reason": item.get("reason"), "status": "critical" if threshold and remaining > threshold else ("warning" if remaining or delayed else "healthy")}
