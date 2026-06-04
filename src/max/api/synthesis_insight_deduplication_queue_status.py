"""JSON API renderer for synthesis insight deduplication queue status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.synthesis_insight_deduplication_queue_status.v1"
KIND = "max.api.synthesis_insight_deduplication_queue_status"
STATUS_RANK = {"critical": 0, "warning": 1, "ok": 2}


def synthesis_insight_deduplication_queue_status_to_json(payload: Mapping[str, Any], *, stale_warning_threshold: int = 1, stale_critical_threshold: int = 5) -> str:
    rows = [_row(item, index, stale_warning_threshold, stale_critical_threshold) for index, item in enumerate(_items(payload), start=1)]
    rows.sort(key=lambda row: (STATUS_RANK[row["status"]], -row["stale_pending_count"], -row["pending_count"], row["profile"], row["batch_id"]))
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"queue_count": len(rows), "pending_count": sum(row["pending_count"] for row in rows), "stale_pending_count": sum(row["stale_pending_count"] for row in rows), "blocked_queue_count": sum(1 for row in rows if row["status"] == "critical")}, "queue_rows": rows, "metadata": source_metadata(payload, queue_count=len(rows))}, indent=2, sort_keys=True)


def _items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list_of_maps(payload.get("queues") or payload.get("rows") or payload.get("items"))


def _row(item: Mapping[str, Any], index: int, warning: int, critical: int) -> dict[str, Any]:
    pending = _count(item.get("pending_count") or item.get("pending"))
    stale = _count(item.get("stale_pending_count") or item.get("stale_pending"))
    processing = _count(item.get("processing_count") or item.get("processing"))
    completed = _count(item.get("completed_count") or item.get("completed"))
    status = "critical" if pending and stale >= max(1, critical) else "warning" if pending and stale >= max(1, warning) else "ok"
    return {"profile": _text(item.get("profile")) or "default", "batch_id": _text(item.get("batch_id") or item.get("batch")) or f"batch-{index}", "pending_count": pending, "stale_pending_count": stale, "processing_count": processing, "completed_count": completed, "oldest_pending_age_minutes": _count(item.get("oldest_pending_age_minutes") or item.get("oldest_age_minutes")), "status": status, "recommendation": _text(item.get("recommendation")) or ("unblock stale deduplication work" if status == "critical" else "inspect queue freshness" if status == "warning" else "none")}


def _count(value: Any) -> int:
    return max(0, int_or_zero(value))


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
