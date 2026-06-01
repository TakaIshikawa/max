"""JSON API renderer for spec generation queue depth status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.spec_generation_queue_depth_status.v1"
KIND = "max.api.spec_generation_queue_depth_status"


def spec_generation_queue_depth_status_to_json(payload: Mapping[str, Any]) -> str:
    depth_threshold = int_or_zero(payload.get("queue_depth_warning_threshold", payload.get("max_pending_jobs", 50)))
    age_threshold = int_or_zero(payload.get("oldest_age_warning_seconds", payload.get("max_queued_age_seconds", 900)))
    rows = [_row(item, index) for index, item in enumerate(list_of_maps(payload.get("jobs") or payload.get("queue") or payload.get("rows")), start=1)]
    counts = {status: sum(1 for row in rows if row["status"] == status) for status in ("pending", "running", "failed", "blocked")}
    queued = [row for row in rows if row["status"] in {"pending", "blocked"}]
    oldest = max((row["queued_age_seconds"] for row in queued), default=0)
    blocked_ratio = round(counts["blocked"] / len(rows), 4) if rows else 0.0
    critical = counts["blocked"] > 0 or oldest > age_threshold or counts["pending"] > depth_threshold
    status = "warning" if critical else "healthy"
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"status": status, "job_count": len(rows), "pending": counts["pending"], "running": counts["running"], "failed": counts["failed"], "blocked": counts["blocked"], "blocked_ratio": blocked_ratio, "oldest_queued_age_seconds": oldest}, "jobs": sorted(rows, key=lambda row: (row["status"] != "blocked", -row["queued_age_seconds"], row["job_id"])), "bottleneck_reasons": _reasons(rows), "metadata": source_metadata(payload)}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _row(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    status = str(item.get("status") or "pending").lower()
    if status not in {"pending", "running", "failed", "blocked"}:
        status = "pending"
    return {"job_id": str(item.get("job_id") or item.get("id") or f"job-{index}"), "status": status, "queued_age_seconds": max(0, int_or_zero(item.get("queued_age_seconds", item.get("age_seconds")))), "reason": str(item.get("reason") or item.get("blocked_reason") or "unspecified")}


def _reasons(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    reasons = sorted({row["reason"] for row in rows if row["status"] in {"blocked", "failed"}})
    result = [{"reason": reason, "count": sum(1 for row in rows if row["reason"] == reason and row["status"] in {"blocked", "failed"})} for reason in reasons]
    return sorted(result, key=lambda row: (-row["count"], row["reason"]))
