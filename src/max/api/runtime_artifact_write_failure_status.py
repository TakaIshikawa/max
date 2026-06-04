"""JSON API renderer for runtime artifact write failure status."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import bool_or_default, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.runtime_artifact_write_failure_status.v1"
KIND = "max.api.runtime_artifact_write_failure_status"
STATUS_RANK = {"critical": 0, "warning": 1, "ok": 2}


def runtime_artifact_write_failure_status_to_json(payload: Mapping[str, Any], *, stale_failure_threshold: int = 3) -> str:
    groups: dict[tuple[str, str, str, str], dict[str, Any]] = defaultdict(lambda: {"retryable": 0, "terminal": 0, "latest": ""})
    for item in _items(payload):
        key = (_text(item.get("artifact_type")) or "unknown", _text(item.get("profile")) or "default", _text(item.get("run_id") or item.get("run")) or "run", _text(item.get("reason") or item.get("failure_reason") or item.get("error_code")) or "unknown")
        retryable = bool_or_default(item.get("retryable"), default=False)
        groups[key]["retryable" if retryable else "terminal"] += 1
        groups[key]["latest"] = max(groups[key]["latest"], _text(item.get("failed_at") or item.get("timestamp") or item.get("created_at")))
    rows = [_row(key, values, stale_failure_threshold) for key, values in groups.items()]
    rows.sort(key=lambda row: (STATUS_RANK[row["status"]], -row["terminal_failure_count"], -row["retryable_failure_count"], row["artifact_type"], row["profile"], row["run_id"]))
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"failure_group_count": len(rows), "retryable_failure_count": sum(row["retryable_failure_count"] for row in rows), "terminal_failure_count": sum(row["terminal_failure_count"] for row in rows), "critical_group_count": sum(1 for row in rows if row["status"] == "critical")}, "failure_rows": rows, "metadata": source_metadata(payload, failure_group_count=len(rows))}, indent=2, sort_keys=True)


def _items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list_of_maps(payload.get("failures") or payload.get("rows") or payload.get("items"))


def _row(key: tuple[str, str, str, str], values: dict[str, Any], stale: int) -> dict[str, Any]:
    artifact_type, profile, run_id, reason = key
    retryable = values["retryable"]
    terminal = values["terminal"]
    status = "critical" if terminal else "warning" if retryable >= stale or retryable else "ok"
    return {"artifact_type": artifact_type, "profile": profile, "run_id": run_id, "failure_reason": reason, "retryable_failure_count": retryable, "terminal_failure_count": terminal, "latest_failure_at": values["latest"] or None, "status": status}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
