"""JSON API renderer for source adapter backfill completeness status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.source_adapter_backfill_completeness_status.v1"
KIND = "max.api.source_adapter_backfill_completeness_status"
STATUS_RANK = {"incomplete": 0, "complete": 1}


def source_adapter_backfill_completeness_status_to_json(payload: Mapping[str, Any], *, completeness_threshold: float = 1.0) -> str:
    rows = [_row(item) for item in list_of_maps(payload.get("adapters") or payload.get("rows") or payload.get("items"))]
    for row in rows:
        row["status"] = "complete" if row["completeness_ratio"] >= completeness_threshold and not row["missing_intervals"] else "incomplete"
    rows.sort(key=lambda row: (STATUS_RANK[row["status"]], row["adapter"]))
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"status": "incomplete" if any(row["status"] == "incomplete" for row in rows) else "complete", "adapter_count": len(rows), "incomplete_count": sum(1 for row in rows if row["status"] == "incomplete")}, "adapters": rows, "metadata": source_metadata(payload, adapter_count=len(rows))}, indent=2, sort_keys=True)


def _row(item: Mapping[str, Any]) -> dict[str, Any]:
    requested = _interval(item.get("requested_range") or item)
    fetched = [_interval(interval) for interval in list_of_maps(item.get("fetched_intervals") or item.get("fetched_ranges"))]
    missing = _missing(requested, fetched)
    requested_len = max(requested[1] - requested[0], 0)
    missing_len = sum(end - start for start, end in missing)
    ratio = round((requested_len - missing_len) / requested_len, 4) if requested_len else 1.0
    return {"adapter": _text(item.get("adapter") or item.get("adapter_id")) or "unknown", "requested_range": {"start": requested[0], "end": requested[1]}, "fetched_range": [{"start": start, "end": end} for start, end in fetched], "missing_intervals": [{"start": start, "end": end} for start, end in missing], "completeness_ratio": ratio, "status": "complete"}


def _missing(requested: tuple[int, int], fetched: list[tuple[int, int]]) -> list[tuple[int, int]]:
    cursor, end = requested
    missing: list[tuple[int, int]] = []
    for start, stop in sorted((max(start, requested[0]), min(stop, end)) for start, stop in fetched if stop > requested[0] and start < end):
        if start > cursor:
            missing.append((cursor, start))
        cursor = max(cursor, stop)
    if cursor < end:
        missing.append((cursor, end))
    return missing


def _interval(value: Any) -> tuple[int, int]:
    item = value if isinstance(value, Mapping) else {}
    return (int(item.get("start", 0) or 0), int(item.get("end", 0) or 0))


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
