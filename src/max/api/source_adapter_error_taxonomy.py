"""JSON API renderer for source adapter error taxonomy reports."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "max.api.source_adapter_error_taxonomy.v1"
KIND = "max.api.source_adapter_error_taxonomy"
SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "unknown": 4}


def source_adapter_error_taxonomy_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    events = _events(payload)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(events),
        "error_types": _error_types(events),
        "affected_sources": _affected_sources(events),
        "retryability": _retryability(events),
        "next_actions": _next_actions(events),
        "metadata": _metadata(payload, events, as_of),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _events(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("error_events")
    if not isinstance(source, list):
        source = payload.get("adapter_errors")
    if not isinstance(source, list):
        source = payload.get("errors")
    rows = [_event(item, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    rows.sort(key=lambda row: (SEVERITY_RANK[row["severity"]], -row["count"], row["source"], row["error_type"], row["adapter"]))
    return rows


def _event(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    return {
        "id": item.get("id") or f"E{index}",
        "adapter": _text(item.get("adapter") or item.get("adapter_name")) or "unknown-adapter",
        "source": _text(item.get("source") or item.get("source_id")) or "unknown-source",
        "error_type": _text(item.get("error_type") or item.get("type") or item.get("code")) or "unknown_error",
        "severity": _severity(item.get("severity")),
        "count": _int(item.get("count", item.get("occurrences", 1))) or 1,
        "retryable": _bool(item.get("retryable", item.get("can_retry"))),
        "message": _text(item.get("message") or item.get("error")),
        "last_seen_at": item.get("last_seen_at") or item.get("occurred_at"),
    }


def _summary(events: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "event_count": len(events),
        "total_error_count": sum(row["count"] for row in events),
        "adapter_count": len({row["adapter"] for row in events}),
        "source_count": len({row["source"] for row in events}),
        "critical_count": sum(row["count"] for row in events if row["severity"] == "critical"),
        "retryable_count": sum(row["count"] for row in events if row["retryable"]),
    }


def _error_types(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        grouped[(event["error_type"], event["severity"])].append(event)
    rows = [
        {
            "error_type": error_type,
            "severity": severity,
            "count": sum(item["count"] for item in items),
            "sources": sorted({item["source"] for item in items}),
            "adapters": sorted({item["adapter"] for item in items}),
        }
        for (error_type, severity), items in grouped.items()
    ]
    rows.sort(key=lambda row: (SEVERITY_RANK[row["severity"]], -row["count"], row["error_type"]))
    return rows


def _affected_sources(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        grouped[event["source"]].append(event)
    rows = [
        {
            "source": source,
            "error_count": sum(item["count"] for item in items),
            "adapters": sorted({item["adapter"] for item in items}),
            "highest_severity": min((item["severity"] for item in items), key=lambda value: SEVERITY_RANK[value]),
        }
        for source, items in grouped.items()
    ]
    rows.sort(key=lambda row: (SEVERITY_RANK[row["highest_severity"]], -row["error_count"], row["source"]))
    return rows


def _retryability(events: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter("retryable" if event["retryable"] else "non_retryable" for event in events for _ in range(event["count"]))
    return {"retryable": counts["retryable"], "non_retryable": counts["non_retryable"]}


def _next_actions(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actions = []
    for event in events:
        if event["severity"] in {"critical", "high"} or not event["retryable"]:
            actions.append(
                {
                    "id": f"inspect-{event['id']}",
                    "source": event["source"],
                    "adapter": event["adapter"],
                    "action": "Inspect adapter error before retry" if not event["retryable"] else "Prioritize adapter recovery",
                    "severity": event["severity"],
                }
            )
    return sorted(actions, key=lambda row: (SEVERITY_RANK[row["severity"]], row["source"], row["adapter"], row["id"]))


def _metadata(payload: Mapping[str, Any], events: list[dict[str, Any]], as_of: str | datetime | None) -> dict[str, Any]:
    metadata = dict(payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {})
    return {**metadata, "source_schema_version": payload.get("schema_version"), "source_kind": payload.get("kind"), "as_of": _as_of(as_of), "event_count": len(events)}


def _severity(value: Any) -> str:
    severity = _text(value).lower()
    return severity if severity in SEVERITY_RANK else "unknown"


def _bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "retryable"}
    return bool(value)


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
