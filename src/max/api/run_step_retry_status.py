"""JSON API renderer for run step retry status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, source_metadata

SCHEMA_VERSION = "max.api.run_step_retry_status.v1"
KIND = "max.api.run_step_retry_status"


def run_step_retry_status_to_json(payload: Mapping[str, Any]) -> str:
    rows = _rows(payload)
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(rows), "rows": rows, "retry_blocked_steps": [row for row in rows if row["exhausted"]], "metadata": source_metadata(payload, step_count=len(rows))}, indent=2, sort_keys=True)


def _rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("steps") if isinstance(payload.get("steps"), list) else payload.get("items")
    rows = [_row(item, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    return sorted(rows, key=lambda row: (not row["exhausted"], -row["attempts"], row["run_id"]))


def _row(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    attempts = max(0, int_or_zero(item.get("attempts")))
    max_attempts = max(0, int_or_zero(item.get("max_attempts")))
    remaining = max(max_attempts - attempts, 0)
    exhausted = bool(max_attempts and attempts >= max_attempts)
    retrying = bool(attempts and not exhausted)
    return {"run_id": _text(item.get("run_id")) or f"run-{index}", "step": _bucket(item.get("step"), "unknown_step"), "attempts": attempts, "max_attempts": max_attempts, "last_error_type": _bucket(item.get("last_error_type"), "none"), "retry_after_seconds": max(0, int_or_zero(item.get("retry_after_seconds"))), "attempts_remaining": remaining, "exhausted": exhausted, "retrying": retrying, "next_action": "escalate" if exhausted else "retry_after_backoff" if retrying else "none"}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    exhausted = sum(1 for row in rows if row["exhausted"])
    retrying = sum(1 for row in rows if row["retrying"])
    return {"status": "exhausted" if exhausted else "retrying" if retrying else "healthy", "step_count": len(rows), "exhausted_count": exhausted, "retrying_count": retrying}


def _bucket(value: Any, default: str) -> str:
    return (_text(value) or default).lower().replace(" ", "_")


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
