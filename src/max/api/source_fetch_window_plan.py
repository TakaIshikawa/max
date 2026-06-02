"""JSON API renderer for planned source fetch windows."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, mapping, source_metadata

SCHEMA_VERSION = "max.api.source_fetch_window_plan.v1"
KIND = "max.api.source_fetch_window_plan"


def source_fetch_window_plan_to_json(payload: Mapping[str, Any]) -> str:
    windows = _windows(payload)
    active = [row for row in windows if not row["skipped"]]
    skipped = [row for row in windows if row["skipped"]]
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "active_count": len(active),
            "skipped_count": len(skipped),
            "budget_limited_count": sum(1 for row in windows if row["skipped_reason"] == "budget_limited"),
            "expected_budget_tokens": sum(row["expected_budget_tokens"] for row in active),
        },
        "fetch_windows": windows,
        "metadata": source_metadata(payload, window_count=len(windows)),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _windows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("windows")
    if not isinstance(source, list):
        source = payload.get("fetch_windows")
    rows = [_window(item, index) for index, item in enumerate(list_of_maps(source), start=1)]
    return sorted(rows, key=lambda row: (row["priority_rank"], row["source"], row["profile"]))


def _window(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    skipped_reason = item.get("skipped_reason") or item.get("skip_reason")
    skipped = bool(skipped_reason or item.get("skipped"))
    priority = str(item.get("priority") or "normal").lower()
    return {
        "id": item.get("id") or f"fetch-window-{index}",
        "source": str(item.get("source") or item.get("source_name") or "unknown-source"),
        "profile": str(item.get("profile") or item.get("profile_id") or "default"),
        "window_start": item.get("window_start") or item.get("start"),
        "window_end": item.get("window_end") or item.get("end"),
        "priority": priority,
        "priority_rank": _priority_rank(priority),
        "reason": item.get("reason"),
        "expected_budget_tokens": int_or_zero(item.get("expected_budget_tokens") or item.get("budget_tokens")),
        "skipped": skipped,
        "skipped_reason": str(skipped_reason) if skipped_reason else None,
        "metadata": dict(mapping(item.get("metadata"))),
    }


def _priority_rank(priority: str) -> int:
    return {"critical": 0, "high": 1, "normal": 2, "low": 3}.get(priority, 4)
