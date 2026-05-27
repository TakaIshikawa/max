"""JSON API renderer for embedding reindex queue status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from max.api._renderer_utils import datetime_to_string, int_or_zero, parse_datetime, source_metadata, strings

SCHEMA_VERSION = "max.api.embedding_reindex_queue_status.v1"
KIND = "max.api.embedding_reindex_queue_status"
STATUS_RANK = {"blocked": 0, "urgent": 1, "queued": 2}
PRIORITY_RANK = {"urgent": 0, "high": 1, "normal": 2, "low": 3}


def embedding_reindex_queue_status_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    now = parse_datetime(as_of) if isinstance(as_of, str) else (as_of if isinstance(as_of, datetime) else None)
    jobs = _jobs(payload, now)
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(jobs), "jobs": jobs, "blocked_jobs": [row for row in jobs if row["status"] == "blocked"], "metadata": source_metadata(payload, as_of=datetime_to_string(now) if isinstance(now, datetime) else as_of, queued_count=len(jobs))}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _jobs(payload: Mapping[str, Any], as_of: datetime | None) -> list[dict[str, Any]]:
    source = payload.get("jobs") if isinstance(payload.get("jobs"), list) else payload.get("items")
    if not isinstance(source, list):
        source = payload.get("queue")
    rows = [_job(item, index, as_of) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    return sorted(rows, key=lambda row: (STATUS_RANK[row["status"]], PRIORITY_RANK.get(row["priority"], 4), -row["age_hours"], row["item_id"]))


def _job(item: Mapping[str, Any], index: int, as_of: datetime | None) -> dict[str, Any]:
    submitted = parse_datetime(item.get("submitted_at") or item.get("enqueued_at") or item.get("queued_at"))
    age = _age_hours(submitted, as_of)
    blocked = strings(item.get("blocked_reasons", item.get("blockers", item.get("blocked_reason"))))
    priority = _bucket(item.get("priority"), "normal")
    status = "blocked" if blocked else ("urgent" if priority == "urgent" or age >= 24 else "queued")
    return {"item_id": _text(item.get("item_id") or item.get("id")) or f"item-{index}", "item_type": _bucket(item.get("item_type") or item.get("type"), "unknown"), "submitted_at": datetime_to_string(submitted), "age_hours": age, "priority": priority, "blocked_reasons": blocked, "status": status}


def _age_hours(submitted: datetime | None, as_of: datetime | None) -> int:
    if submitted is None or as_of is None:
        return 0
    current = as_of if as_of.tzinfo else as_of.replace(tzinfo=timezone.utc)
    return max(int((current.astimezone(timezone.utc) - submitted).total_seconds() // 3600), 0)


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    blocked = sum(1 for row in rows if row["status"] == "blocked")
    urgent = sum(1 for row in rows if row["status"] == "urgent")
    oldest = max((row["age_hours"] for row in rows), default=0)
    status = "blocked" if blocked else ("urgent" if urgent else ("queued" if rows else "empty"))
    return {"status": status, "queued_count": len(rows), "blocked_count": blocked, "urgent_count": urgent, "oldest_age_hours": oldest}


def _bucket(value: Any, default: str) -> str:
    return (_text(value) or default).lower().replace(" ", "_")


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
