"""JSON API renderer for synthesis throughput status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import float_or_zero, int_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.synthesis_throughput_status.v1"
KIND = "max.api.synthesis_throughput_status"
STATUS_RANK = {"stalled": 0, "degraded": 1, "healthy": 2, "idle": 3}


def synthesis_throughput_status_to_json(payload: Mapping[str, Any], *, minimum_throughput_per_hour: float = 10, backlog_warning_threshold: int = 100) -> str:
    rows = [_row(item, index, minimum_throughput_per_hour, backlog_warning_threshold) for index, item in enumerate(list_of_maps(payload.get("windows") or payload.get("rows") or payload.get("items")), start=1)]
    rows.sort(key=lambda row: (STATUS_RANK[row["status"]], row["profile"], row["window"]))
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"status": "stalled" if any(row["status"] == "stalled" for row in rows) else "degraded" if any(row["status"] == "degraded" for row in rows) else "healthy" if rows else "idle", "window_count": len(rows), "backlog_count": sum(row["backlog_count"] for row in rows)}, "windows": rows, "metadata": source_metadata(payload, window_count=len(rows))}, indent=2, sort_keys=True)


def _row(item: Mapping[str, Any], index: int, minimum: float, backlog_warning: int) -> dict[str, Any]:
    signals = max(0, int_or_zero(item.get("signals_processed", item.get("signals"))))
    insights = max(0, int_or_zero(item.get("insights_generated", item.get("insights"))))
    hours = max(0.0, float_or_zero(item.get("window_hours", item.get("duration_hours"))))
    if not hours:
        hours = max(0.0, float_or_zero(item.get("window_minutes", item.get("duration_minutes"))) / 60)
    throughput = round(signals / hours, 4) if hours else 0.0
    backlog = max(0, int_or_zero(item.get("backlog_count", item.get("backlog"))))
    status = "stalled" if hours and signals == 0 and backlog else "degraded" if (hours and throughput < minimum) or backlog >= backlog_warning else "healthy"
    return {"profile": _text(item.get("profile")) or "default", "window": _text(item.get("window")) or f"window-{index}", "signals_processed": signals, "insights_generated": insights, "throughput_per_hour": throughput, "backlog_count": backlog, "status": status}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
