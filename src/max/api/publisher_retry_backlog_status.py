"""JSON API renderer for publisher retry backlog status."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from max.api._renderer_utils import bool_or_default, int_or_zero, list_of_maps, parse_datetime, source_metadata

SCHEMA_VERSION = "max.api.publisher_retry_backlog_status.v1"
KIND = "max.api.publisher_retry_backlog_status"
STATUS_RANK = {"blocked": 0, "delayed": 1, "healthy": 2}


def publisher_retry_backlog_status_to_json(payload: Mapping[str, Any] | Sequence[Mapping[str, Any]], *, as_of: datetime | str | None = None, delayed_minutes: int = 60) -> str:
    now = parse_datetime(as_of) if as_of is not None else datetime.now(timezone.utc)
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for item in _items(payload):
        key = (_text(item.get("destination")) or "unknown", _text(item.get("channel")) or "default")
        group = groups.setdefault(key, {"destination": key[0], "channel": key[1], "pending_count": 0, "oldest_retry_age_minutes": 0, "next_retry_due_count": 0, "exhausted_retry_count": 0})
        group["pending_count"] += 1
        created = parse_datetime(item.get("created_at") or item.get("first_retry_at") or item.get("retry_at"))
        if created is not None:
            group["oldest_retry_age_minutes"] = max(group["oldest_retry_age_minutes"], int((now - created).total_seconds() // 60))
        due = parse_datetime(item.get("next_retry_at"))
        if due is not None and due <= now:
            group["next_retry_due_count"] += 1
        if bool_or_default(item.get("exhausted", item.get("retry_exhausted")), default=False) or int_or_zero(item.get("attempts")) >= int_or_zero(item.get("max_attempts")) > 0:
            group["exhausted_retry_count"] += 1
    rows = [_finish_group(group, delayed_minutes) for group in groups.values()]
    rows.sort(key=lambda row: (STATUS_RANK[row["status"]], row["destination"], row["channel"]))
    metadata = source_metadata(payload if isinstance(payload, Mapping) else {}, group_count=len(rows))
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(rows), "retry_backlog": rows, "metadata": metadata}, indent=2, sort_keys=True)


def _finish_group(group: dict[str, Any], delayed_minutes: int) -> dict[str, Any]:
    status = "blocked" if group["exhausted_retry_count"] else "delayed" if group["oldest_retry_age_minutes"] >= delayed_minutes or group["next_retry_due_count"] else "healthy"
    return {**group, "status": status}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"status": "blocked" if any(row["status"] == "blocked" for row in rows) else "delayed" if any(row["status"] == "delayed" for row in rows) else "healthy", "group_count": len(rows), "pending_count": sum(row["pending_count"] for row in rows), "next_retry_due_count": sum(row["next_retry_due_count"] for row in rows), "exhausted_retry_count": sum(row["exhausted_retry_count"] for row in rows)}


def _items(payload: Mapping[str, Any] | Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    if isinstance(payload, Mapping):
        return list_of_maps(payload.get("retries") or payload.get("queue") or payload.get("rows") or payload.get("items"))
    return [item for item in payload if isinstance(item, Mapping)]


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
