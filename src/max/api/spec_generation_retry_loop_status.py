"""JSON API renderer for spec generation retry loop status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, source_metadata

SCHEMA_VERSION = "max.api.spec_generation_retry_loop_status.v1"
KIND = "max.api.spec_generation_retry_loop_status"
STATUS_RANK = {"critical": 0, "warning": 1, "ok": 2}


def spec_generation_retry_loop_status_to_json(payload: Mapping[str, Any], *, warning_attempts: int = 2, critical_attempts: int = 4) -> str:
    rows = _rows(payload, warning_attempts, critical_attempts)
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"total_jobs": len(rows), "retry_loop_candidates": sum(1 for row in rows if row["status"] != "ok"), "critical_jobs": sum(1 for row in rows if row["status"] == "critical"), "max_attempts": max((row["attempts"] for row in rows), default=0)}, "job_rows": rows, "metadata": source_metadata(payload, job_count=len(rows))}, indent=2, sort_keys=True)


def _rows(payload: Mapping[str, Any], warning: int, critical: int) -> list[dict[str, Any]]:
    source = payload.get("jobs") or payload.get("queue") or payload.get("items") or payload
    if isinstance(source, Mapping):
        items = [{**dict(value), "job_id": value.get("job_id") or key} for key, value in source.items() if isinstance(value, Mapping)]
    elif isinstance(source, list):
        items = [item for item in source if isinstance(item, Mapping)]
    else:
        items = []
    rows = [_row(item, index, warning, critical) for index, item in enumerate(items, start=1)]
    return sorted(rows, key=lambda row: (STATUS_RANK[row["status"]], -row["attempts"], row["job_id"], row["unit_id"]))


def _row(item: Mapping[str, Any], index: int, warning: int, critical: int) -> dict[str, Any]:
    attempts = max(0, int_or_zero(item.get("attempts", item.get("retry_count"))))
    has_error = bool(_text(item.get("last_error")))
    status = "critical" if attempts >= critical and has_error else "warning" if attempts >= warning and has_error else "ok"
    unit_id = _text(item.get("unit_id"))
    return {"job_id": _text(item.get("job_id") or item.get("id")) or unit_id or f"job-{index}", "unit_id": unit_id or None, "attempts": attempts, "last_error": _text(item.get("last_error") or item.get("error")) or None, "last_attempt_at": item.get("last_attempt_at"), "status": status}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
