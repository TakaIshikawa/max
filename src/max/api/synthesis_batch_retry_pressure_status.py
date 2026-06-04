"""JSON API renderer for synthesis batch retry pressure status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.synthesis_batch_retry_pressure_status.v1"
KIND = "max.api.synthesis_batch_retry_pressure_status"
STATUS_RANK = {"critical": 0, "warning": 1, "ok": 2}


def synthesis_batch_retry_pressure_status_to_json(payload: Mapping[str, Any], *, warning_retry_threshold: int = 2, critical_retry_threshold: int = 5) -> str:
    rows = [_row(item, index, warning_retry_threshold, critical_retry_threshold) for index, item in enumerate(_items(payload), start=1)]
    rows.sort(key=lambda row: (STATUS_RANK[row["status"]], -row["retry_count"], row["profile"], row["batch_id"]))
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"batch_count": len(rows), "retry_count": sum(row["retry_count"] for row in rows), "critical_batch_count": sum(1 for row in rows if row["status"] == "critical"), "warning_batch_count": sum(1 for row in rows if row["status"] == "warning")}, "batch_rows": rows, "metadata": source_metadata(payload, batch_count=len(rows))}, indent=2, sort_keys=True)


def _items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list_of_maps(payload.get("batches") or payload.get("rows") or payload.get("items"))


def _row(item: Mapping[str, Any], index: int, warning: int, critical: int) -> dict[str, Any]:
    retries = max(0, int_or_zero(item.get("retry_count") or item.get("retries")))
    failed = max(0, int_or_zero(item.get("failed_attempt_count") or item.get("failed_attempts")))
    status = "critical" if retries >= critical else "warning" if retries >= warning or failed else "ok"
    return {"profile": _text(item.get("profile")) or "default", "batch_id": _text(item.get("batch_id") or item.get("batch")) or f"batch-{index}", "retry_count": retries, "failed_attempt_count": failed, "last_retry_at": _text(item.get("last_retry_at") or item.get("updated_at")) or None, "status": status, "recommendation": "pause and inspect retry pressure" if status == "critical" else "monitor retry trend" if status == "warning" else "none"}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
