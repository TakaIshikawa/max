"""JSON API renderer for LLM rate limit queue status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, source_metadata

SCHEMA_VERSION = "max.api.llm_rate_limit_queue_status.v1"
KIND = "max.api.llm_rate_limit_queue_status"
STATUS_RANK = {"critical": 0, "warning": 1, "ok": 2}


def llm_rate_limit_queue_status_to_json(payload: Mapping[str, Any], *, warning_wait_seconds: int = 60, critical_wait_seconds: int = 300) -> str:
    rows = _rows(payload, warning_wait_seconds, critical_wait_seconds)
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"total_queues": len(rows), "providers_under_pressure": len({row["provider"] for row in rows if row["status"] != "ok"}), "critical_queues": sum(1 for row in rows if row["status"] == "critical"), "max_effective_wait_seconds": max((row["effective_wait_seconds"] for row in rows), default=0)}, "queue_rows": rows, "metadata": source_metadata(payload, queue_count=len(rows))}, indent=2, sort_keys=True)


def _rows(payload: Mapping[str, Any], warning: int, critical: int) -> list[dict[str, Any]]:
    source = payload.get("queues") or payload.get("models") or payload.get("items") or payload
    if isinstance(source, Mapping):
        items = [{**dict(value), "provider": value.get("provider") or key} for key, value in source.items() if isinstance(value, Mapping)]
    elif isinstance(source, list):
        items = [item for item in source if isinstance(item, Mapping)]
    else:
        items = []
    rows = [_row(item, index, warning, critical) for index, item in enumerate(items, start=1)]
    return sorted(rows, key=lambda row: (STATUS_RANK[row["status"]], -row["effective_wait_seconds"], row["provider"], row["model"]))


def _row(item: Mapping[str, Any], index: int, warning: int, critical: int) -> dict[str, Any]:
    queued = max(0, int_or_zero(item.get("queued_requests", item.get("queue_depth"))))
    retry_after = max(0, int_or_zero(item.get("retry_after_seconds")))
    oldest = max(0, int_or_zero(item.get("oldest_wait_seconds")))
    effective = max(retry_after, oldest) if queued else 0
    status = "critical" if effective >= critical else "warning" if effective >= warning else "ok"
    return {"provider": _text(item.get("provider")) or f"provider-{index}", "model": _text(item.get("model")) or "all", "queued_requests": queued, "retry_after_seconds": retry_after, "oldest_wait_seconds": oldest, "effective_wait_seconds": effective, "status": status}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
