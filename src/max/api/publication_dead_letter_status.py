"""JSON API renderer for publication dead letter status."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "max.api.publication_dead_letter_status.v1"
KIND = "max.api.publication_dead_letter_status"
STATUS_RANK = {"exhausted": 0, "blocked": 1, "retryable": 2, "archived": 3}


def publication_dead_letter_status_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    messages = _messages(payload)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(messages),
        "messages": messages,
        "exhausted_messages": [row for row in messages if row["status"] == "exhausted"],
        "destination_totals": _totals(messages, "destination"),
        "error_totals": _totals(messages, "last_error"),
        "metadata": _metadata(payload, messages, as_of),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _messages(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("messages") if isinstance(payload.get("messages"), list) else payload.get("dead_letters")
    rows = [_message(item, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    rows.sort(key=lambda row: (STATUS_RANK[row["status"]], row["destination"], row["message_id"]))
    return rows


def _message(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    attempts = _int(item.get("attempts", item.get("attempt_count")))
    max_attempts = max(1, _int(item.get("max_attempts", item.get("attempt_limit"))) or 1)
    retryable = _bool(item.get("retryable", True))
    archived = _bool(item.get("archived")) or _text(item.get("state")).lower() == "archived"
    status = "archived" if archived else ("exhausted" if attempts >= max_attempts else ("retryable" if retryable else "blocked"))
    return {
        "message_id": _text(item.get("message_id") or item.get("id")) or f"message-{index}",
        "destination": _text(item.get("destination")) or "unknown-destination",
        "idea_id": _text(item.get("idea_id") or item.get("idea")) or "unknown-idea",
        "attempts": attempts,
        "max_attempts": max_attempts,
        "last_error": _text(item.get("last_error") or item.get("error")) or "unknown-error",
        "retryable": retryable,
        "age_minutes": _int(item.get("age_minutes", item.get("age"))),
        "status": status,
    }


def _summary(messages: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row["status"] for row in messages)
    return {"message_count": len(messages), "retryable_count": counts["retryable"], "exhausted_count": counts["exhausted"], "blocked_count": counts["blocked"], "archived_count": counts["archived"]}


def _totals(messages: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in messages:
        grouped[row[field]].append(row)
    return [{field: key, "message_count": len(items), "exhausted_count": sum(1 for item in items if item["status"] == "exhausted")} for key, items in sorted(grouped.items())]


def _metadata(payload: Mapping[str, Any], messages: list[dict[str, Any]], as_of: str | datetime | None) -> dict[str, Any]:
    metadata = dict(payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {})
    return {**metadata, "source_schema_version": payload.get("schema_version"), "source_kind": payload.get("kind"), "as_of": _as_of(as_of), "message_count": len(messages)}


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def _bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _as_of(value: str | datetime | None) -> str | None:
    if isinstance(value, datetime):
        parsed = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return value


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
