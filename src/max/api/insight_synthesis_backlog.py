"""JSON API renderer for insight synthesis backlog status."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from max.api._renderer_utils import (
    age_bucket,
    as_list,
    datetime_to_string,
    float_or_zero,
    int_or_zero,
    list_of_maps,
    mapping,
    parse_datetime,
    source_metadata,
    strings,
)


SCHEMA_VERSION = "max.api.insight_synthesis_backlog.v1"
KIND = "max.api.insight_synthesis_backlog"
AGE_BUCKETS = ("0_1d", "2_7d", "8_30d", "over_30d", "unknown")


def insight_synthesis_backlog_to_json(
    payload: Mapping[str, Any],
    *,
    as_of: str | datetime | None = None,
) -> str:
    effective_as_of = parse_datetime(as_of) or parse_datetime(payload.get("as_of"))
    items = _backlog_items(payload, effective_as_of)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(payload, items),
        "backlog_items": items,
        "by_source": _by_group(payload, items, "by_source", "source"),
        "by_profile": _by_group(payload, items, "by_profile", "profile"),
        "stale_batches": _stale_batches(payload, items),
        "blockers": _blockers(payload, items),
        "token_estimates": _token_estimates(payload, items),
        "metadata": source_metadata(
            payload,
            as_of=mapping(payload.get("metadata")).get("as_of") or datetime_to_string(effective_as_of),
            backlog_item_count=len(items),
        ),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _backlog_items(payload: Mapping[str, Any], as_of: datetime | None) -> list[dict[str, Any]]:
    source = payload.get("backlog_items")
    if not isinstance(source, list):
        source = payload.get("signal_batches")
    if not isinstance(source, list):
        source = payload.get("unsynthesized_batches")
    rows = [
        _item(item, index, as_of)
        for index, item in enumerate(source if isinstance(source, list) else [], start=1)
        if isinstance(item, Mapping)
    ]
    return sorted(rows, key=lambda row: (str(row["batch_id"]), str(row["source"]), str(row["profile"])))


def _item(item: Mapping[str, Any], index: int, as_of: datetime | None) -> dict[str, Any]:
    created_at = item.get("created_at") or item.get("received_at")
    blocker_reasons = strings(
        item.get("blocker_reasons")
        if item.get("blocker_reasons") is not None
        else item.get("blockers")
    )
    return {
        "batch_id": item.get("batch_id") or item.get("id") or f"B{index}",
        "source": item.get("source") or item.get("source_id") or "unknown",
        "profile": item.get("profile") or item.get("profile_id") or "unknown",
        "signal_count": int_or_zero(item.get("signal_count", item.get("signals_count"))),
        "created_at": created_at,
        "age_bucket": age_bucket(created_at, as_of),
        "token_estimate": int_or_zero(item.get("token_estimate", item.get("estimated_tokens"))),
        "blocker_reasons": blocker_reasons,
        "blocked": bool(blocker_reasons) or bool(item.get("blocked")),
        "metadata": dict(mapping(item.get("metadata"))),
    }


def _summary(payload: Mapping[str, Any], items: list[dict[str, Any]]) -> dict[str, Any]:
    source = mapping(payload.get("summary"))
    return {
        "total_batches": int_or_zero(source.get("total_batches", len(items))),
        "total_signals": int_or_zero(source.get("total_signals", sum(item["signal_count"] for item in items))),
        "blocked_batches": int_or_zero(source.get("blocked_batches", sum(1 for item in items if item["blocked"]))),
        "estimated_tokens": int_or_zero(source.get("estimated_tokens", sum(item["token_estimate"] for item in items))),
    }


def _by_group(
    payload: Mapping[str, Any],
    items: list[dict[str, Any]],
    field: str,
    key_name: str,
) -> list[dict[str, Any]]:
    explicit = list_of_maps(payload.get(field))
    if explicit:
        return sorted(
            [
                {
                    key_name: item.get(key_name) or item.get("name") or "unknown",
                    "batch_count": int_or_zero(item.get("batch_count")),
                    "signal_count": int_or_zero(item.get("signal_count")),
                    "token_estimate": int_or_zero(item.get("token_estimate")),
                }
                for item in explicit
            ],
            key=lambda row: str(row[key_name]),
        )
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        grouped[str(item[key_name] or "unknown")].append(item)
    return [
        {
            key_name: key,
            "batch_count": len(rows),
            "signal_count": sum(row["signal_count"] for row in rows),
            "token_estimate": sum(row["token_estimate"] for row in rows),
        }
        for key, rows in sorted(grouped.items())
    ]


def _stale_batches(payload: Mapping[str, Any], items: list[dict[str, Any]]) -> dict[str, int] | list[dict[str, Any]]:
    explicit = list_of_maps(payload.get("stale_batches"))
    if explicit:
        return sorted(
            [{"batch_id": item.get("batch_id") or item.get("id") or f"S{index}", "age_bucket": item.get("age_bucket") or "unknown"} for index, item in enumerate(explicit, start=1)],
            key=lambda row: (str(row["age_bucket"]), str(row["batch_id"])),
        )
    counts = Counter(str(item["age_bucket"]) for item in items)
    return {bucket: counts[bucket] for bucket in AGE_BUCKETS}


def _blockers(payload: Mapping[str, Any], items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    explicit = list_of_maps(payload.get("blockers"))
    if explicit:
        return sorted(
            [{"batch_id": item.get("batch_id") or item.get("id") or f"K{index}", "reasons": strings(item.get("reasons") or item.get("blocker_reasons"))} for index, item in enumerate(explicit, start=1)],
            key=lambda row: str(row["batch_id"]),
        )
    return [
        {"batch_id": item["batch_id"], "reasons": item["blocker_reasons"]}
        for item in items
        if item["blocker_reasons"]
    ]


def _token_estimates(payload: Mapping[str, Any], items: list[dict[str, Any]]) -> dict[str, Any]:
    explicit = mapping(payload.get("token_estimates"))
    by_batch = {str(item["batch_id"]): item["token_estimate"] for item in items}
    return {
        "total": int_or_zero(explicit.get("total", sum(by_batch.values()))),
        "average_per_batch": round(float_or_zero(explicit.get("average_per_batch", (sum(by_batch.values()) / len(items)) if items else 0)), 2),
        "by_batch": dict(sorted(by_batch.items())),
    }
