"""JSON API renderer for source fetch starvation status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, source_metadata

SCHEMA_VERSION = "max.api.source_fetch_starvation_status.v1"
KIND = "max.api.source_fetch_starvation_status"


def source_fetch_starvation_status_to_json(payload: Mapping[str, Any]) -> str:
    rows = _rows(payload)
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(rows), "rows": rows, "starved_sources": [row for row in rows if row["starved"]], "metadata": source_metadata(payload, source_count=len(rows))}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("sources") if isinstance(payload.get("sources"), list) else payload.get("items")
    rows = [_row(item) for item in source if isinstance(item, Mapping)] if isinstance(source, list) else []
    return sorted(rows, key=lambda row: (not row["starved"], -row["starvation_gap"], row["source"]))


def _row(item: Mapping[str, Any]) -> dict[str, Any]:
    allocated = max(0, int_or_zero(item.get("allocated_fetches")))
    completed = max(0, int_or_zero(item.get("completed_fetches")))
    skipped = max(0, int_or_zero(item.get("skipped_fetches")))
    target = max(0, int_or_zero(item.get("target_min_fetches")))
    effective = completed + skipped
    gap = max(0, target - effective)
    return {"source": _bucket(item.get("source"), "unknown_source"), "allocated_fetches": allocated, "completed_fetches": completed, "skipped_fetches": skipped, "target_min_fetches": target, "starvation_gap": gap, "starved": bool(gap)}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"status": "starved" if any(row["starved"] for row in rows) else "satisfied", "source_count": len(rows), "total_allocated": sum(row["allocated_fetches"] for row in rows), "total_completed": sum(row["completed_fetches"] for row in rows), "total_skipped": sum(row["skipped_fetches"] for row in rows), "starved_count": sum(1 for row in rows if row["starved"])}


def _bucket(value: Any, default: str) -> str:
    text = " ".join(str(value).strip().split()) if value is not None else ""
    return (text or default).lower().replace(" ", "_")
