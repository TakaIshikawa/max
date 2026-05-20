"""JSON API renderer for publication queue status reports."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any


SCHEMA_VERSION = "max.api.publication_queue_status.v1"
KIND = "max.api.publication_queue_status"
AGE_BUCKETS = ("0_1d", "2_7d", "8_30d", "over_30d", "unknown")
READY_STATUSES = {"queued", "pending", "ready", "published_ready"}
RETRY_STATUSES = {"retry", "retrying", "retryable"}
BLOCKED_STATUSES = {"blocked", "paused", "held"}


def publication_queue_status_to_json(
    payload: Mapping[str, Any],
    *,
    as_of: str | datetime | None = None,
) -> str:
    """Render publication queue status data as deterministic API JSON."""
    effective_as_of = _parse_datetime(as_of) or _parse_datetime(payload.get("as_of"))
    specs = _queued_specs(payload, effective_as_of)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(payload, specs),
        "queued_specs": specs,
        "destinations": _destinations(payload, specs),
        "retry_state": _retry_state(payload, specs, effective_as_of),
        "blocked_items": _blocked_items(payload, specs),
        "owner_hints": _owner_hints(payload, specs),
        "age_buckets": _age_buckets(specs),
        "next_actions": _next_actions(payload, specs),
        "metadata": _metadata(payload, specs, effective_as_of),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _summary(payload: Mapping[str, Any], specs: list[dict[str, Any]]) -> dict[str, Any]:
    source = _mapping(payload.get("summary"))
    status_counts = Counter(str(row["status"]) for row in specs)
    return {
        "queued_count": _int_or_zero(
            source.get("queued_count", sum(status_counts[status] for status in READY_STATUSES))
        ),
        "retrying_count": _int_or_zero(
            source.get("retrying_count", sum(status_counts[status] for status in RETRY_STATUSES))
        ),
        "blocked_count": _int_or_zero(
            source.get("blocked_count", sum(status_counts[status] for status in BLOCKED_STATUSES))
        ),
        "published_ready_count": _int_or_zero(
            source.get("published_ready_count", status_counts["published_ready"])
        ),
        "total_count": _int_or_zero(source.get("total_count", len(specs))),
    }


def _queued_specs(
    payload: Mapping[str, Any],
    as_of: datetime | None,
) -> list[dict[str, Any]]:
    source = payload.get("queued_specs")
    if not isinstance(source, list):
        source = payload.get("queue_items")
    if not isinstance(source, list):
        source = payload.get("publication_queue")

    rows = [
        _spec_row(item, index, as_of)
        for index, item in enumerate(source if isinstance(source, list) else [], start=1)
        if isinstance(item, Mapping)
    ]
    return sorted(
        rows,
        key=lambda row: (
            str(row["spec_id"] or ""),
            str(row["destination"] or ""),
            str(row["status"] or ""),
        ),
    )


def _spec_row(item: Mapping[str, Any], index: int, as_of: datetime | None) -> dict[str, Any]:
    status = str(item.get("status") or "queued")
    next_retry_at = item.get("next_retry_at")
    return {
        "spec_id": item.get("spec_id") or item.get("id") or f"Q{index}",
        "title": item.get("title") or item.get("name"),
        "destination": item.get("destination") or item.get("target_type") or "unknown",
        "target_url": item.get("target_url") or item.get("url"),
        "status": status,
        "owner": item.get("owner"),
        "enqueued_at": item.get("enqueued_at") or item.get("created_at"),
        "age_bucket": _age_bucket(item.get("enqueued_at") or item.get("created_at"), as_of),
        "attempt_count": _int_or_zero(item.get("attempt_count")),
        "next_retry_at": next_retry_at,
        "retry_eligible": _retry_eligible(status, next_retry_at, as_of),
        "blocker_reasons": _blocker_reasons(item),
        "metadata": dict(_mapping(item.get("metadata"))),
    }


def _destinations(payload: Mapping[str, Any], specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    explicit = _list_of_maps(payload.get("destinations"))
    if explicit:
        return sorted(
            [
                {
                    "destination": item.get("destination") or item.get("target_type") or "unknown",
                    "queued_count": _int_or_zero(item.get("queued_count")),
                    "retrying_count": _int_or_zero(item.get("retrying_count")),
                    "blocked_count": _int_or_zero(item.get("blocked_count")),
                    "published_ready_count": _int_or_zero(item.get("published_ready_count")),
                }
                for item in explicit
            ],
            key=lambda row: str(row["destination"]),
        )

    grouped: dict[str, list[dict[str, Any]]] = {}
    for spec in specs:
        grouped.setdefault(str(spec["destination"] or "unknown"), []).append(spec)
    return [
        {
            "destination": destination,
            "queued_count": sum(1 for spec in rows if spec["status"] in READY_STATUSES),
            "retrying_count": sum(1 for spec in rows if spec["status"] in RETRY_STATUSES),
            "blocked_count": sum(1 for spec in rows if spec["status"] in BLOCKED_STATUSES),
            "published_ready_count": sum(1 for spec in rows if spec["status"] == "published_ready"),
        }
        for destination, rows in sorted(grouped.items())
    ]


def _retry_state(
    payload: Mapping[str, Any],
    specs: list[dict[str, Any]],
    as_of: datetime | None,
) -> dict[str, Any]:
    explicit = _mapping(payload.get("retry_state"))
    retrying = [spec for spec in specs if spec["status"] in RETRY_STATUSES]
    eligible = [spec for spec in retrying if spec["retry_eligible"]]
    return {
        "as_of": explicit.get("as_of") or _datetime_to_string(as_of),
        "retrying_count": _int_or_zero(explicit.get("retrying_count", len(retrying))),
        "eligible_retry_count": _int_or_zero(explicit.get("eligible_retry_count", len(eligible))),
        "next_retry_at": explicit.get("next_retry_at") or _min_string(
            spec.get("next_retry_at") for spec in retrying
        ),
    }


def _blocked_items(payload: Mapping[str, Any], specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    explicit = _list_of_maps(payload.get("blocked_items"))
    if explicit:
        return sorted(
            [
                {
                    "spec_id": item.get("spec_id") or item.get("id") or f"B{index}",
                    "destination": item.get("destination") or item.get("target_type"),
                    "owner": item.get("owner"),
                    "blocker_reasons": _blocker_reasons(item),
                }
                for index, item in enumerate(explicit, start=1)
            ],
            key=lambda row: (str(row["spec_id"] or ""), str(row["destination"] or "")),
        )

    return [
        {
            "spec_id": spec["spec_id"],
            "destination": spec["destination"],
            "owner": spec["owner"],
            "blocker_reasons": spec["blocker_reasons"],
        }
        for spec in specs
        if spec["status"] in BLOCKED_STATUSES or spec["blocker_reasons"]
    ]


def _owner_hints(payload: Mapping[str, Any], specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    explicit = _list_of_maps(payload.get("owner_hints"))
    if explicit:
        return sorted(
            [
                {
                    "owner": item.get("owner") or item.get("name"),
                    "spec_ids": sorted(str(value) for value in _as_list(item.get("spec_ids"))),
                    "reason": item.get("reason"),
                }
                for item in explicit
            ],
            key=lambda row: str(row["owner"] or ""),
        )

    grouped: dict[str, list[str]] = {}
    for spec in specs:
        owner = spec.get("owner")
        if owner:
            grouped.setdefault(str(owner), []).append(str(spec["spec_id"]))
    return [
        {"owner": owner, "spec_ids": sorted(spec_ids), "reason": None}
        for owner, spec_ids in sorted(grouped.items())
    ]


def _age_buckets(specs: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(str(spec["age_bucket"]) for spec in specs)
    return {bucket: counts[bucket] for bucket in AGE_BUCKETS}


def _next_actions(payload: Mapping[str, Any], specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    explicit = _list_of_maps(payload.get("next_actions"))
    if explicit:
        return [
            {
                "id": item.get("id") or f"A{index}",
                "action": item.get("action") or item.get("title") or item.get("description"),
                "owner": item.get("owner"),
                "spec_id": item.get("spec_id"),
            }
            for index, item in enumerate(explicit, start=1)
        ]

    actions = []
    for spec in specs:
        if spec["status"] in BLOCKED_STATUSES:
            actions.append(
                {
                    "id": f"unblock-{spec['spec_id']}",
                    "action": "Resolve publication blocker",
                    "owner": spec["owner"],
                    "spec_id": spec["spec_id"],
                }
            )
        elif spec["retry_eligible"]:
            actions.append(
                {
                    "id": f"retry-{spec['spec_id']}",
                    "action": "Retry publication",
                    "owner": spec["owner"],
                    "spec_id": spec["spec_id"],
                }
            )
    return sorted(actions, key=lambda row: str(row["id"]))


def _metadata(
    payload: Mapping[str, Any],
    specs: list[dict[str, Any]],
    as_of: datetime | None,
) -> dict[str, Any]:
    metadata = dict(_mapping(payload.get("metadata")))
    return {
        **metadata,
        "source_schema_version": metadata.get("source_schema_version")
        or payload.get("schema_version"),
        "source_kind": metadata.get("source_kind") or payload.get("kind"),
        "as_of": metadata.get("as_of") or _datetime_to_string(as_of),
        "queued_spec_count": len(specs),
        "destination_count": len({str(spec["destination"]) for spec in specs}),
    }


def _blocker_reasons(item: Mapping[str, Any]) -> list[str]:
    value = item.get("blocker_reasons")
    if value is None:
        value = item.get("blockers")
    if value is None:
        value = item.get("blocked_reason")
    if value is None:
        value = item.get("blocker")
    return sorted({str(reason) for reason in _as_list(value) if reason not in (None, "")})


def _retry_eligible(status: str, next_retry_at: Any, as_of: datetime | None) -> bool:
    if status not in RETRY_STATUSES:
        return False
    retry_at = _parse_datetime(next_retry_at)
    if retry_at is None or as_of is None:
        return False
    return retry_at <= as_of


def _age_bucket(value: Any, as_of: datetime | None) -> str:
    created_at = _parse_datetime(value)
    if created_at is None or as_of is None:
        return "unknown"
    days = max((as_of - created_at).days, 0)
    if days <= 1:
        return "0_1d"
    if days <= 7:
        return "2_7d"
    if days <= 30:
        return "8_30d"
    return "over_30d"


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _datetime_to_string(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat().replace("+00:00", "Z")


def _min_string(values: Any) -> str | None:
    candidates = sorted(str(value) for value in values if value)
    return candidates[0] if candidates else None


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list_of_maps(value: Any) -> list[Mapping[str, Any]]:
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def _int_or_zero(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
