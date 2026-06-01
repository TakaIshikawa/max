"""JSON API renderer for source adapter throttle window status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.source_adapter_throttle_window_status.v1"
KIND = "max.api.source_adapter_throttle_window_status"
STATUS_RANK = {"critical": 0, "warning": 1, "healthy": 2}


def source_adapter_throttle_window_status_to_json(payload: Mapping[str, Any]) -> str:
    rows = [_row(item, index) for index, item in enumerate(_items(payload), start=1)]
    rows.sort(key=lambda row: (STATUS_RANK[row["status"]], -row["remaining_seconds"], row["adapter"]))
    throttled = [row for row in rows if row["throttled"]]
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(rows, throttled),
        "adapters": rows,
        "throttled_adapters": throttled,
        "next_reset": min((row["reset_at"] for row in throttled if row["reset_at"] != "unknown"), default="unknown"),
        "metadata": source_metadata(payload, adapter_count=len(rows)),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    metadata = payload.get("metadata")
    nested = metadata.get("source_adapter_throttle_window") if isinstance(metadata, Mapping) else None
    if isinstance(nested, Mapping):
        return list_of_maps(nested.get("adapters") or nested.get("throttles"))
    return list_of_maps(payload.get("adapters") or payload.get("throttles") or payload.get("incidents"))


def _row(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    remaining = int_or_zero(item.get("remaining_seconds", item.get("reset_after_seconds", item.get("retry_after_seconds"))))
    window = int_or_zero(item.get("window_seconds", item.get("throttle_window_seconds")))
    reset_at = str(item.get("reset_at") or "unknown")
    throttled = bool(item.get("throttled", item.get("blocked", False))) or remaining > 0 or str(item.get("status") or "").lower() in {"throttled", "blocked", "overdue"}
    overdue = bool(item.get("overdue")) or str(item.get("status") or "").lower() == "overdue"
    status = "critical" if overdue or str(item.get("status") or "").lower() == "blocked" else ("warning" if throttled else "healthy")
    return {
        "id": str(item.get("id") or item.get("adapter") or item.get("name") or f"adapter-{index}"),
        "adapter": str(item.get("adapter") or item.get("name") or item.get("id") or f"adapter-{index}"),
        "reset_at": reset_at,
        "reset_after_seconds": remaining,
        "remaining_seconds": remaining,
        "window_seconds": window,
        "throttled": throttled,
        "overdue": overdue,
        "status": status,
    }


def _summary(rows: list[dict[str, Any]], throttled: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"status": "no_data", "adapter_count": 0, "throttled_count": 0, "critical_count": 0}
    status = "critical" if any(row["status"] == "critical" for row in rows) else ("warning" if throttled else "healthy")
    return {"status": status, "adapter_count": len(rows), "throttled_count": len(throttled), "critical_count": sum(1 for row in rows if row["status"] == "critical")}
