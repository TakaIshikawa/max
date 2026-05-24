"""JSON API renderer for spec generation queue status."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from max.api._renderer_utils import age_bucket, as_list, datetime_to_string, int_or_zero, list_of_maps, mapping, parse_datetime, source_metadata, strings


SCHEMA_VERSION = "max.api.spec_generation_queue_status.v1"
KIND = "max.api.spec_generation_queue_status"
AGE_BUCKETS = ("0_1d", "2_7d", "8_30d", "over_30d", "unknown")
READY_STATUSES = {"ready", "approved", "queued"}
BLOCKED_STATUSES = {"blocked", "needs_input", "paused"}
GENERATED_STATUSES = {"generated", "completed", "done"}


def spec_generation_queue_status_to_json(
    payload: Mapping[str, Any],
    *,
    as_of: str | datetime | None = None,
) -> str:
    effective_as_of = parse_datetime(as_of) or parse_datetime(payload.get("as_of"))
    items = _queue_items(payload, effective_as_of)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(payload, items),
        "queue_items": items,
        "template_mix": _template_mix(payload, items),
        "blocked_items": _blocked_items(payload, items),
        "owner_hints": _owner_hints(payload, items),
        "age_buckets": _age_buckets(items),
        "next_actions": _next_actions(payload, items),
        "metadata": source_metadata(payload, as_of=mapping(payload.get("metadata")).get("as_of") or datetime_to_string(effective_as_of), queue_item_count=len(items)),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _queue_items(payload: Mapping[str, Any], as_of: datetime | None) -> list[dict[str, Any]]:
    source = payload.get("queue_items")
    if not isinstance(source, list):
        source = payload.get("approved_ideas")
    if not isinstance(source, list):
        source = payload.get("spec_generation_queue")
    rows = [_item(item, index, as_of) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    return sorted(rows, key=lambda row: (str(row["idea_id"]), str(row["template"]), str(row["status"])))


def _item(item: Mapping[str, Any], index: int, as_of: datetime | None) -> dict[str, Any]:
    status = str(item.get("status") or ("blocked" if item.get("blocked_reason") or item.get("blocker_reasons") else "ready"))
    approved_at = item.get("approved_at") or item.get("created_at") or item.get("queued_at")
    blockers = strings(item.get("blocker_reasons") if item.get("blocker_reasons") is not None else item.get("blocked_reason"))
    return {
        "idea_id": item.get("idea_id") or item.get("id") or f"I{index}",
        "title": item.get("title") or item.get("name"),
        "status": status,
        "template": item.get("template") or item.get("template_id") or "default",
        "owner": item.get("owner") or item.get("assignee"),
        "approved_at": approved_at,
        "age_bucket": age_bucket(approved_at, as_of),
        "blocker_reasons": blockers,
        "ready": status in READY_STATUSES and not blockers,
        "metadata": dict(mapping(item.get("metadata"))),
    }


def _summary(payload: Mapping[str, Any], items: list[dict[str, Any]]) -> dict[str, int]:
    source = mapping(payload.get("summary"))
    counts = Counter(str(item["status"]) for item in items)
    return {
        "ready_count": int_or_zero(source.get("ready_count", sum(counts[status] for status in READY_STATUSES))),
        "blocked_count": int_or_zero(source.get("blocked_count", sum(counts[status] for status in BLOCKED_STATUSES))),
        "generated_count": int_or_zero(source.get("generated_count", sum(counts[status] for status in GENERATED_STATUSES))),
        "total_count": int_or_zero(source.get("total_count", len(items))),
    }


def _template_mix(payload: Mapping[str, Any], items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    explicit = list_of_maps(payload.get("template_mix"))
    if explicit:
        return sorted([{"template": item.get("template") or item.get("template_id") or "default", "count": int_or_zero(item.get("count"))} for item in explicit], key=lambda row: str(row["template"]))
    counts = Counter(str(item["template"]) for item in items)
    return [{"template": key, "count": counts[key]} for key in sorted(counts)]


def _blocked_items(payload: Mapping[str, Any], items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    explicit = list_of_maps(payload.get("blocked_items"))
    if explicit:
        return sorted([{"idea_id": item.get("idea_id") or item.get("id") or f"B{index}", "owner": item.get("owner"), "blocker_reasons": strings(item.get("blocker_reasons") or item.get("reasons"))} for index, item in enumerate(explicit, start=1)], key=lambda row: str(row["idea_id"]))
    return [{"idea_id": item["idea_id"], "owner": item["owner"], "blocker_reasons": item["blocker_reasons"]} for item in items if item["status"] in BLOCKED_STATUSES or item["blocker_reasons"]]


def _owner_hints(payload: Mapping[str, Any], items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    explicit = list_of_maps(payload.get("owner_hints"))
    if explicit:
        return sorted([{"owner": item.get("owner") or item.get("name"), "idea_ids": sorted(str(value) for value in as_list(item.get("idea_ids"))), "reason": item.get("reason")} for item in explicit], key=lambda row: str(row["owner"] or ""))
    grouped: dict[str, list[str]] = defaultdict(list)
    for item in items:
        if item["owner"]:
            grouped[str(item["owner"])].append(str(item["idea_id"]))
    return [{"owner": owner, "idea_ids": sorted(ids), "reason": None} for owner, ids in sorted(grouped.items())]


def _age_buckets(items: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(str(item["age_bucket"]) for item in items)
    return {bucket: counts[bucket] for bucket in AGE_BUCKETS}


def _next_actions(payload: Mapping[str, Any], items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    explicit = list_of_maps(payload.get("next_actions"))
    if explicit:
        return sorted([{"id": item.get("id") or f"A{index}", "action": item.get("action") or item.get("title"), "owner": item.get("owner"), "idea_id": item.get("idea_id")} for index, item in enumerate(explicit, start=1)], key=lambda row: str(row["id"]))
    return sorted([{"id": f"unblock-{item['idea_id']}", "action": "Resolve spec generation blocker", "owner": item["owner"], "idea_id": item["idea_id"]} for item in items if item["status"] in BLOCKED_STATUSES or item["blocker_reasons"]], key=lambda row: str(row["id"]))
