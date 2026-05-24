"""JSON API renderer for feedback learning queue status."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "max.api.feedback_learning_queue_status.v1"
KIND = "max.api.feedback_learning_queue_status"
STATUS_RANK = {"failed": 0, "delayed": 1, "processing": 2, "queued": 3}
PRIORITIES = {"low", "normal", "high", "urgent"}


def feedback_learning_queue_status_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    items = _items(payload)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(items),
        "items": items,
        "failed_items": [row for row in items if row["status"] == "failed"],
        "profile_totals": _totals(items, "profile"),
        "outcome_totals": _totals(items, "outcome"),
        "metadata": _metadata(payload, items, as_of),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _items(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("items") if isinstance(payload.get("items"), list) else payload.get("queue")
    rows = [_item(item, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    rows.sort(key=lambda row: (STATUS_RANK[row["status"]], row["profile"], row["feedback_id"]))
    return rows


def _item(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    age_hours = _int(item.get("age_hours", item.get("age")))
    attempts = _int(item.get("attempts", item.get("attempt_count")))
    last_error = _text(item.get("last_error") or item.get("error"))
    state = _text(item.get("state") or item.get("status")).lower()
    status = _status(state, attempts, last_error, age_hours)
    return {
        "feedback_id": _text(item.get("feedback_id") or item.get("id")) or f"feedback-{index}",
        "idea_id": _text(item.get("idea_id") or item.get("idea")) or "unknown-idea",
        "profile": _text(item.get("profile")) or "unknown-profile",
        "outcome": _text(item.get("outcome")) or "unknown-outcome",
        "age_hours": age_hours,
        "attempts": attempts,
        "last_error": last_error,
        "priority": _priority(item.get("priority")),
        "status": status,
    }


def _status(state: str, attempts: int, last_error: str, age_hours: int) -> str:
    if state == "processing":
        return "processing"
    if state == "failed" or attempts >= 3 or (last_error and attempts > 0):
        return "failed"
    if state == "delayed" or age_hours >= 24:
        return "delayed"
    return "queued"


def _summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row["status"] for row in items)
    return {"item_count": len(items), "queued_count": counts["queued"], "processing_count": counts["processing"], "delayed_count": counts["delayed"], "failed_count": counts["failed"]}


def _totals(items: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in items:
        grouped[row[field]].append(row)
    return [{field: key, "item_count": len(values), "failed_count": sum(1 for item in values if item["status"] == "failed")} for key, values in sorted(grouped.items())]


def _metadata(payload: Mapping[str, Any], items: list[dict[str, Any]], as_of: str | datetime | None) -> dict[str, Any]:
    metadata = dict(payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {})
    return {**metadata, "source_schema_version": payload.get("schema_version"), "source_kind": payload.get("kind"), "as_of": _as_of(as_of), "item_count": len(items)}


def _priority(value: Any) -> str:
    text = _text(value).lower()
    return text if text in PRIORITIES else "normal"


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def _as_of(value: str | datetime | None) -> str | None:
    if isinstance(value, datetime):
        parsed = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return value


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
