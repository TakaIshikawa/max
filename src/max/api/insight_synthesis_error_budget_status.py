"""JSON API renderer for insight synthesis error budget status."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import list_of_maps, mapping, source_metadata

SCHEMA_VERSION = "max.api.insight_synthesis_error_budget_status.v1"
KIND = "max.api.insight_synthesis_error_budget_status"
STATUS_RANK = {"critical": 0, "warning": 1, "ok": 2}


def insight_synthesis_error_budget_status_to_json(records: Any, *, failure_threshold: float = 0.2, error_budget: float = 0.1) -> str:
    payload = mapping(records)
    source = payload.get("attempts") or payload.get("records") or payload.get("items") or (records if isinstance(records, list) else [])
    groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for item in list_of_maps(source):
        groups[_text(item.get("profile_id") or item.get("run_id") or item.get("id")) or "unknown"].append(item)
    rows = [_row(key, attempts, failure_threshold, error_budget) for key, attempts in groups.items()]
    rows.sort(key=lambda row: (STATUS_RANK[row["status"]], row["remaining_error_budget"], row["group_id"]))
    status = _overall(rows)
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "status": status, "summary": {"group_count": len(rows), "attempt_count": sum(row["attempt_count"] for row in rows), "failure_count": sum(row["failure_count"] for row in rows), "status": status}, "groups": rows, "metadata": source_metadata(payload, group_count=len(rows))}, indent=2, sort_keys=True)


def _row(group_id: str, attempts: list[Mapping[str, Any]], threshold: float, budget: float) -> dict[str, Any]:
    failures = sum(1 for item in attempts if _failed(item))
    total = len(attempts)
    ratio = round(failures / total, 4) if total else 0.0
    remaining = round(max(budget - ratio, 0.0), 4)
    status = "critical" if total and (remaining == 0.0 or ratio > threshold) else ("warning" if ratio else "ok")
    return {"group_id": group_id, "attempt_count": total, "failure_count": failures, "failure_ratio": ratio, "remaining_error_budget": remaining, "status": status}


def _failed(item: Mapping[str, Any]) -> bool:
    status = _text(item.get("status") or item.get("outcome")).casefold()
    return bool(item.get("failed")) or status in {"failed", "failure", "error", "timeout"}


def _overall(rows: list[dict[str, Any]]) -> str:
    if any(row["status"] == "critical" for row in rows):
        return "critical"
    if any(row["status"] == "warning" for row in rows):
        return "warning"
    return "ok"


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
