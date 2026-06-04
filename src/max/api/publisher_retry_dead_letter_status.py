"""JSON API renderer for publisher retry dead-letter status."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import datetime_to_string, list_of_maps, mapping, parse_datetime, source_metadata

SCHEMA_VERSION = "max.api.publisher_retry_dead_letter_status.v1"
KIND = "max.api.publisher_retry_dead_letter_status"
STATUS_RANK = {"critical": 0, "warning": 1, "ok": 2}


def publisher_retry_dead_letter_status_to_json(records: Any, *, critical_count: int = 3) -> str:
    payload = mapping(records)
    source = payload.get("dead_letters") or payload.get("records") or payload.get("items") or (records if isinstance(records, list) else [])
    groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for item in list_of_maps(source):
        groups[_text(item.get("destination") or item.get("destination_id")) or "unknown"].append(item)
    rows = [_row(destination, items, critical_count) for destination, items in groups.items()]
    rows.sort(key=lambda row: (STATUS_RANK[row["status"]], -row["dead_letter_count"], row["destination"]))
    status = _overall(rows)
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "status": status, "summary": {"destination_count": len(rows), "dead_letter_count": sum(row["dead_letter_count"] for row in rows), "status": status}, "destinations": rows, "metadata": source_metadata(payload, destination_count=len(rows))}, indent=2, sort_keys=True)


def _row(destination: str, items: list[Mapping[str, Any]], critical_count: int) -> dict[str, Any]:
    reasons = Counter(_text(item.get("reason") or item.get("error_reason")) or "unknown" for item in items)
    times = [parse_datetime(item.get("dead_lettered_at") or item.get("failed_at") or item.get("created_at")) for item in items]
    valid = [value for value in times if value is not None]
    count = len(items)
    status = "critical" if count >= critical_count else ("warning" if count else "ok")
    return {"destination": destination, "dead_letter_count": count, "oldest_dead_lettered_at": datetime_to_string(min(valid) if valid else None), "top_reason": reasons.most_common(1)[0][0] if reasons else "unknown", "status": status}


def _overall(rows: list[dict[str, Any]]) -> str:
    if any(row["status"] == "critical" for row in rows):
        return "critical"
    if any(row["status"] == "warning" for row in rows):
        return "warning"
    return "ok"


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
