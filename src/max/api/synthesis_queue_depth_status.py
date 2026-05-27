"""JSON API renderer for synthesis queue depth status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, source_metadata

SCHEMA_VERSION = "max.api.synthesis_queue_depth_status.v1"
KIND = "max.api.synthesis_queue_depth_status"


def synthesis_queue_depth_status_to_json(payload: Mapping[str, Any]) -> str:
    rows = _rows(payload)
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(rows), "rows": rows, "metadata": source_metadata(payload, queue_count=len(rows))}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("queues") if isinstance(payload.get("queues"), list) else payload.get("items")
    rows = [_row(item) for item in source if isinstance(item, Mapping)] if isinstance(source, list) else []
    return sorted(rows, key=lambda row: (not row["delayed"], -row["failed_count"], row["profile"], row["priority"]))


def _row(item: Mapping[str, Any]) -> dict[str, Any]:
    pending = max(0, int_or_zero(item.get("pending_count")))
    processing = max(0, int_or_zero(item.get("processing_count")))
    failed = max(0, int_or_zero(item.get("failed_count")))
    oldest = max(0, int_or_zero(item.get("oldest_pending_minutes")))
    target = max(0, int_or_zero(item.get("target_drain_minutes")))
    return {"profile": _bucket(item.get("profile"), "default"), "priority": _bucket(item.get("priority"), "normal"), "pending_count": pending, "processing_count": processing, "failed_count": failed, "oldest_pending_minutes": oldest, "target_drain_minutes": target, "backlog_ratio": round(oldest / target, 4) if target else (1.0 if pending else 0.0), "delayed": bool(target and oldest > target)}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    blocked = sorted({row["profile"] for row in rows if row["delayed"] or row["failed_count"]})
    pending = sum(row["pending_count"] for row in rows)
    processing = sum(row["processing_count"] for row in rows)
    failed = sum(row["failed_count"] for row in rows)
    return {"status": "blocked" if blocked else "healthy", "total_pending": pending, "total_processing": processing, "total_failed": failed, "backlog_ratio": round(pending / max(processing, 1), 4) if pending else 0.0, "blocked_profiles": blocked}


def _bucket(value: Any, default: str) -> str:
    text = " ".join(str(value).strip().split()) if value is not None else ""
    return (text or default).lower().replace(" ", "_")
