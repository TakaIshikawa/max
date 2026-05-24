"""JSON API renderer for idea review queue status."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from max.api._renderer_utils import (
    age_bucket,
    as_list,
    datetime_to_string,
    int_or_zero,
    list_of_maps,
    mapping,
    parse_datetime,
    source_metadata,
    strings,
)


SCHEMA_VERSION = "max.api.idea_review_queue_status.v1"
KIND = "max.api.idea_review_queue_status"
AGE_BUCKETS = ("0_1d", "2_7d", "8_30d", "over_30d", "unknown")
PENDING_STATUSES = {"pending", "queued", "reviewing", "in_review"}
REVIEWED_STATUSES = {"reviewed", "approved", "rejected", "accepted"}
ESCALATED_STATUSES = {"escalated", "blocked"}


def idea_review_queue_status_to_json(
    payload: Mapping[str, Any],
    *,
    as_of: str | datetime | None = None,
) -> str:
    """Render idea review queue status data as deterministic API JSON."""
    effective_as_of = parse_datetime(as_of) or parse_datetime(payload.get("as_of"))
    items = _review_items(payload, effective_as_of)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(payload, items),
        "review_items": items,
        "reviewer_load": _reviewer_load(payload, items),
        "stale_items": _stale_items(payload, items),
        "recommendation_counts": _recommendation_counts(payload, items),
        "next_actions": _next_actions(payload, items),
        "metadata": _metadata(payload, items, effective_as_of),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _summary(payload: Mapping[str, Any], items: list[dict[str, Any]]) -> dict[str, Any]:
    source = mapping(payload.get("summary"))
    counts = Counter(str(item["status"]) for item in items)
    return {
        "pending_count": int_or_zero(
            source.get("pending_count", sum(counts[status] for status in PENDING_STATUSES))
        ),
        "reviewed_count": int_or_zero(
            source.get("reviewed_count", sum(counts[status] for status in REVIEWED_STATUSES))
        ),
        "escalated_count": int_or_zero(
            source.get("escalated_count", sum(counts[status] for status in ESCALATED_STATUSES))
        ),
        "total_count": int_or_zero(source.get("total_count", len(items))),
    }


def _review_items(payload: Mapping[str, Any], as_of: datetime | None) -> list[dict[str, Any]]:
    source = payload.get("review_items")
    if not isinstance(source, list):
        source = payload.get("ideas")
    if not isinstance(source, list):
        source = payload.get("idea_review_queue")
    rows = [
        _review_item(item, index, as_of)
        for index, item in enumerate(source if isinstance(source, list) else [], start=1)
        if isinstance(item, Mapping)
    ]
    return sorted(rows, key=lambda row: (str(row["idea_id"]), str(row["reviewer"] or ""), str(row["status"])))


def _review_item(item: Mapping[str, Any], index: int, as_of: datetime | None) -> dict[str, Any]:
    submitted_at = item.get("submitted_at") or item.get("created_at") or item.get("queued_at")
    status = str(item.get("status") or "pending")
    return {
        "idea_id": item.get("idea_id") or item.get("id") or f"I{index}",
        "title": item.get("title") or item.get("name"),
        "status": status,
        "reviewer": item.get("reviewer") or item.get("owner") or item.get("assignee"),
        "submitted_at": submitted_at,
        "age_bucket": age_bucket(submitted_at, as_of),
        "recommendation": item.get("recommendation") or item.get("decision"),
        "escalation_reasons": strings(
            item.get("escalation_reasons")
            if item.get("escalation_reasons") is not None
            else item.get("blocker_reasons")
        ),
        "metadata": dict(mapping(item.get("metadata"))),
    }


def _reviewer_load(payload: Mapping[str, Any], items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    explicit = list_of_maps(payload.get("reviewer_load"))
    if explicit:
        return sorted(
            [
                {
                    "reviewer": item.get("reviewer") or item.get("owner") or item.get("name"),
                    "pending_count": int_or_zero(item.get("pending_count")),
                    "reviewed_count": int_or_zero(item.get("reviewed_count")),
                    "escalated_count": int_or_zero(item.get("escalated_count")),
                    "idea_ids": sorted(str(value) for value in as_list(item.get("idea_ids"))),
                }
                for item in explicit
            ],
            key=lambda row: str(row["reviewer"] or ""),
        )
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        reviewer = str(item.get("reviewer") or "unassigned")
        grouped.setdefault(reviewer, []).append(item)
    return [
        {
            "reviewer": reviewer,
            "pending_count": sum(1 for item in rows if item["status"] in PENDING_STATUSES),
            "reviewed_count": sum(1 for item in rows if item["status"] in REVIEWED_STATUSES),
            "escalated_count": sum(1 for item in rows if item["status"] in ESCALATED_STATUSES),
            "idea_ids": sorted(str(item["idea_id"]) for item in rows),
        }
        for reviewer, rows in sorted(grouped.items())
    ]


def _stale_items(payload: Mapping[str, Any], items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    explicit = list_of_maps(payload.get("stale_items"))
    if explicit:
        return sorted(
            [
                {
                    "idea_id": item.get("idea_id") or item.get("id") or f"S{index}",
                    "reviewer": item.get("reviewer") or item.get("owner"),
                    "age_bucket": item.get("age_bucket") or "unknown",
                    "reason": item.get("reason"),
                }
                for index, item in enumerate(explicit, start=1)
            ],
            key=lambda row: (str(row["age_bucket"]), str(row["idea_id"])),
        )
    return [
        {
            "idea_id": item["idea_id"],
            "reviewer": item["reviewer"],
            "age_bucket": item["age_bucket"],
            "reason": "review_age",
        }
        for item in items
        if item["status"] in PENDING_STATUSES and item["age_bucket"] in {"8_30d", "over_30d"}
    ]


def _recommendation_counts(payload: Mapping[str, Any], items: list[dict[str, Any]]) -> dict[str, int]:
    explicit = mapping(payload.get("recommendation_counts"))
    if explicit:
        return {str(key): int_or_zero(value) for key, value in sorted(explicit.items())}
    counts = Counter(str(item["recommendation"] or "none") for item in items)
    return dict(sorted((key, counts[key]) for key in counts))


def _next_actions(payload: Mapping[str, Any], items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    explicit = list_of_maps(payload.get("next_actions"))
    if explicit:
        return sorted(
            [
                {
                    "id": item.get("id") or f"A{index}",
                    "action": item.get("action") or item.get("title"),
                    "owner": item.get("owner") or item.get("reviewer"),
                    "idea_id": item.get("idea_id"),
                }
                for index, item in enumerate(explicit, start=1)
            ],
            key=lambda row: str(row["id"]),
        )
    actions = []
    for item in items:
        if item["status"] in ESCALATED_STATUSES:
            actions.append(
                {
                    "id": f"resolve-{item['idea_id']}",
                    "action": "Resolve escalated idea review",
                    "owner": item["reviewer"],
                    "idea_id": item["idea_id"],
                }
            )
        elif item["status"] in PENDING_STATUSES and item["age_bucket"] in {"8_30d", "over_30d"}:
            actions.append(
                {
                    "id": f"review-{item['idea_id']}",
                    "action": "Complete stale idea review",
                    "owner": item["reviewer"],
                    "idea_id": item["idea_id"],
                }
            )
    return sorted(actions, key=lambda row: str(row["id"]))


def _metadata(
    payload: Mapping[str, Any],
    items: list[dict[str, Any]],
    as_of: datetime | None,
) -> dict[str, Any]:
    return source_metadata(
        payload,
        as_of=mapping(payload.get("metadata")).get("as_of") or datetime_to_string(as_of),
        review_item_count=len(items),
        reviewer_count=len({str(item.get("reviewer") or "unassigned") for item in items}),
    )
