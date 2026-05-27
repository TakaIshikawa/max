"""JSON API renderer for inference queue saturation status."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from max.api._renderer_utils import datetime_to_string, float_or_zero, int_or_zero, source_metadata

SCHEMA_VERSION = "max.api.inference_queue_saturation_status.v1"
KIND = "max.api.inference_queue_saturation_status"
STATUS_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def inference_queue_saturation_status_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    queues = _queues(payload)
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(queues), "queues": queues, "status_totals": _status_totals(queues), "metadata": source_metadata(payload, as_of=datetime_to_string(as_of) if isinstance(as_of, datetime) else as_of, queue_count=len(queues))}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _queues(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("queues") if isinstance(payload.get("queues"), list) else payload.get("queue_metrics")
    rows = [_queue(item, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    return sorted(rows, key=lambda row: (STATUS_RANK[row["status"]], -row["oldest_job_age_minutes"], -row["utilization"], row["queue_name"]))


def _queue(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    pending = max(0, int_or_zero(item.get("pending_jobs", item.get("pending"))))
    running = max(0, int_or_zero(item.get("running_jobs", item.get("running"))))
    oldest = max(0, int_or_zero(item.get("oldest_job_age_minutes", item.get("oldest_age_minutes"))))
    capacity = max(0, int_or_zero(item.get("capacity")))
    utilization = _utilization(item.get("utilization"), pending, running, capacity)
    status = _status(item.get("status"), oldest, utilization)
    return {"queue_name": _text(item.get("queue_name") or item.get("queue")) or f"queue-{index}", "pending_jobs": pending, "running_jobs": running, "oldest_job_age_minutes": oldest, "capacity": capacity, "utilization": utilization, "status": status}


def _utilization(value: Any, pending: int, running: int, capacity: int) -> float:
    raw = float_or_zero(value) if value is not None else ((pending + running) / capacity if capacity else 0.0)
    return round(min(max(raw, 0.0), 1.0), 4)


def _status(value: Any, oldest: int, utilization: float) -> str:
    explicit = _bucket(value, "")
    if explicit in STATUS_RANK:
        return explicit
    if oldest >= 120 or utilization >= 0.98:
        return "critical"
    if oldest >= 60 or utilization >= 0.9:
        return "high"
    if oldest >= 15 or utilization >= 0.75:
        return "medium"
    return "low"


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row["status"] for row in rows)
    return {"status": "critical" if counts["critical"] else ("high" if counts["high"] else ("medium" if counts["medium"] else "low")), "queue_count": len(rows), "saturated_count": sum(1 for row in rows if row["status"] in {"critical", "high"}), "max_oldest_job_age_minutes": max((row["oldest_job_age_minutes"] for row in rows), default=0)}


def _status_totals(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(row["status"] for row in rows)
    return [{"status": status, "queue_count": counts[status]} for status in ("critical", "high", "medium", "low")]


def _bucket(value: Any, default: str) -> str:
    return (_text(value) or default).lower().replace(" ", "_")


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
