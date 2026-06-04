"""JSON API renderer for source fetch freshness status."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any

from max.api._renderer_utils import datetime_to_string, list_of_maps, mapping, parse_datetime, source_metadata

SCHEMA_VERSION = "max.api.source_fetch_freshness_status.v1"
KIND = "max.api.source_fetch_freshness_status"
STATUS_RANK = {"critical": 0, "warning": 1, "ok": 2}


def source_fetch_freshness_status_to_json(records: Any, *, now: str | datetime | None = None, stale_after_hours: int = 24) -> str:
    payload = mapping(records)
    source = payload.get("records") or payload.get("fetches") or payload.get("items") or (records if isinstance(records, list) else [])
    effective_now = parse_datetime(now) or parse_datetime(payload.get("now")) or datetime.now().astimezone()
    cutoff = effective_now - timedelta(hours=max(1, int(stale_after_hours)))
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for item in list_of_maps(source):
        grouped[_text(item.get("source") or item.get("source_id")) or "unknown"].append(item)
    rows = [_source_row(source_id, rows, cutoff) for source_id, rows in grouped.items()]
    rows.sort(key=lambda row: (STATUS_RANK[row["status"]], -row["stale_ratio"], row["source"]))
    status = _overall(rows)
    output = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "status": status,
        "summary": {
            "source_count": len(rows),
            "total_count": sum(row["total_count"] for row in rows),
            "stale_count": sum(row["stale_count"] for row in rows),
            "malformed_timestamp_count": sum(row["malformed_timestamp_count"] for row in rows),
            "status": status,
        },
        "sources": rows,
        "metadata": source_metadata(payload, source_count=len(rows), as_of=datetime_to_string(effective_now)),
    }
    return json.dumps(output, indent=2, sort_keys=True)


def _source_row(source: str, rows: list[Mapping[str, Any]], cutoff: datetime) -> dict[str, Any]:
    parsed = [parse_datetime(row.get("seen_at") or row.get("fetched_at") or row.get("timestamp")) for row in rows]
    valid = [value for value in parsed if value is not None]
    malformed = len(parsed) - len(valid)
    stale = sum(1 for value in valid if value < cutoff) + malformed
    total = len(rows)
    stale_ratio = round(stale / total, 4) if total else 0.0
    status = "critical" if stale_ratio >= 0.5 else ("warning" if stale else "ok")
    return {"source": source, "newest_seen_at": datetime_to_string(max(valid) if valid else None), "oldest_seen_at": datetime_to_string(min(valid) if valid else None), "stale_count": stale, "total_count": total, "stale_ratio": stale_ratio, "malformed_timestamp_count": malformed, "status": status}


def _overall(rows: list[dict[str, Any]]) -> str:
    if any(row["status"] == "critical" for row in rows):
        return "critical"
    if any(row["status"] == "warning" for row in rows):
        return "warning"
    return "ok"


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
