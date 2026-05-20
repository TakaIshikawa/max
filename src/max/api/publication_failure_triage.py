"""JSON API renderer for publication failure triage reports."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from typing import Any


SCHEMA_VERSION = "max.api.publication_failure_triage.v1"
KIND = "max.api.publication_failure_triage"
RETRYABLE_STATUSES = {408, 409, 425, 429, 500, 502, 503, 504}
RETRYABLE_PRIORITIES = {"p0", "p1", "retry", "retryable"}


def publication_failure_triage_to_json(payload: Mapping[str, Any]) -> str:
    """Render publication failure triage data as deterministic API JSON."""
    failures = _failures(payload)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(payload, failures),
        "failures": failures,
        "categories": _categories(payload, failures),
        "retryable_failures": _retryable_failures(payload, failures),
        "destination_health": _destination_health(payload, failures),
        "owner_assignments": _owner_assignments(payload, failures),
        "escalation_actions": _escalation_actions(payload),
        "metadata": _metadata(payload, failures),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _summary(payload: Mapping[str, Any], failures: list[dict[str, Any]]) -> dict[str, Any]:
    source = _mapping(payload.get("summary"))
    retryable_count = _int_or_none(source.get("retryable_failure_count"))
    if retryable_count is None:
        retryable_count = sum(1 for row in failures if row["retryable"])

    return {
        "attempt_count": _int_or_zero(source.get("attempt_count")),
        "failure_count": _int_or_zero(
            source.get("failure_count", source.get("failure_attempt_count", len(failures)))
        ),
        "open_failure_count": _int_or_zero(source.get("open_failure_count", len(failures))),
        "affected_idea_count": _int_or_zero(source.get("affected_idea_count")),
        "retryable_failure_count": retryable_count,
    }


def _failures(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("failures")
    if not isinstance(source, list):
        source = payload.get("failed_publications")
    if not isinstance(source, list):
        source = payload.get("failure_groups")

    rows = []
    for index, item in enumerate(source if isinstance(source, list) else [], start=1):
        if not isinstance(item, Mapping):
            continue
        row = {
            "id": item.get("id") or item.get("failure_id") or f"F{index}",
            "idea_id": item.get("idea_id"),
            "target_type": item.get("target_type") or item.get("destination") or "unknown",
            "target_url": item.get("target_url"),
            "status": item.get("status") or "failed",
            "category": (
                item.get("category")
                or item.get("failure_category")
                or item.get("target_type")
                or "unknown"
            ),
            "error": item.get("error") or item.get("latest_error"),
            "failed_at": (
                item.get("failed_at")
                or item.get("latest_failure_at")
                or item.get("created_at")
            ),
            "response_status": item.get("response_status"),
            "open_failure_count": _int_or_zero(item.get("open_failure_count", 1)),
            "owner": item.get("owner"),
            "retryable": _is_retryable(item),
        }
        rows.append(row)

    return sorted(
        rows,
        key=lambda row: (
            str(row["target_type"]),
            str(row.get("target_url") or ""),
            str(row.get("status") or ""),
            str(row.get("id") or ""),
        ),
    )


def _categories(payload: Mapping[str, Any], failures: list[dict[str, Any]]) -> list[dict[str, Any]]:
    source = payload.get("categories") or payload.get("failure_categories")
    if isinstance(source, list):
        return [
            {
                "category": str(item.get("category") or item.get("name") or "unknown"),
                "count": _int_or_zero(item.get("count")),
                "retryable_count": _int_or_zero(item.get("retryable_count")),
            }
            for item in source
            if isinstance(item, Mapping)
        ]

    counts = Counter(str(row.get("category") or "unknown") for row in failures)
    retryable_counts = Counter(
        str(row.get("category") or "unknown") for row in failures if row["retryable"]
    )
    return [
        {
            "category": category,
            "count": counts[category],
            "retryable_count": retryable_counts[category],
        }
        for category in sorted(counts)
    ]


def _retryable_failures(
    payload: Mapping[str, Any],
    failures: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    source = payload.get("retryable_failures")
    if isinstance(source, list):
        return [
            _retryable_row(item, index)
            for index, item in enumerate(source, start=1)
            if isinstance(item, Mapping)
        ]
    return [
        {
            "id": row["id"],
            "target_type": row["target_type"],
            "target_url": row["target_url"],
            "reason": row["error"] or row["status"],
        }
        for row in failures
        if row["retryable"]
    ]


def _retryable_row(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    return {
        "id": item.get("id") or item.get("failure_id") or f"R{index}",
        "target_type": item.get("target_type") or item.get("destination") or "unknown",
        "target_url": item.get("target_url"),
        "reason": item.get("reason") or item.get("error"),
    }


def _destination_health(
    payload: Mapping[str, Any],
    failures: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    source = payload.get("destination_health")
    if isinstance(source, list):
        return [
            {
                "target_type": item.get("target_type") or item.get("destination") or "unknown",
                "status": item.get("status"),
                "open_failure_count": _int_or_zero(item.get("open_failure_count")),
                "latest_failure_at": item.get("latest_failure_at"),
            }
            for item in source
            if isinstance(item, Mapping)
        ]

    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in failures:
        grouped.setdefault(str(row["target_type"]), []).append(row)
    return [
        {
            "target_type": target_type,
            "status": "degraded" if rows else "healthy",
            "open_failure_count": sum(_int_or_zero(row.get("open_failure_count")) for row in rows),
            "latest_failure_at": max(
                (str(row.get("failed_at") or "") for row in rows),
                default=None,
            )
            or None,
        }
        for target_type, rows in sorted(grouped.items())
    ]


def _owner_assignments(
    payload: Mapping[str, Any],
    failures: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    source = payload.get("owner_assignments")
    if isinstance(source, list):
        return [
            {
                "owner": item.get("owner") or item.get("name"),
                "target_type": item.get("target_type") or item.get("destination"),
                "failure_ids": [str(value) for value in _as_list(item.get("failure_ids"))],
            }
            for item in source
            if isinstance(item, Mapping)
        ]

    grouped: dict[str, list[str]] = {}
    for row in failures:
        owner = row.get("owner")
        if owner:
            grouped.setdefault(str(owner), []).append(str(row["id"]))
    return [
        {"owner": owner, "target_type": None, "failure_ids": sorted(ids)}
        for owner, ids in sorted(grouped.items())
    ]


def _escalation_actions(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "id": item.get("id") or f"E{index}",
            "action": item.get("action") or item.get("title") or item.get("description"),
            "owner": item.get("owner"),
            "due_at": item.get("due_at") or item.get("due_date"),
        }
        for index, item in enumerate(_list_of_maps(payload.get("escalation_actions")), start=1)
    ]


def _metadata(payload: Mapping[str, Any], failures: list[dict[str, Any]]) -> dict[str, Any]:
    metadata = dict(_mapping(payload.get("metadata")))
    return {
        **metadata,
        "source_schema_version": metadata.get("source_schema_version")
        or payload.get("schema_version"),
        "source_kind": metadata.get("source_kind") or payload.get("kind"),
        "failure_count": len(failures),
        "category_count": len(_categories(payload, failures)),
        "retryable_failure_count": len(_retryable_failures(payload, failures)),
    }


def _is_retryable(item: Mapping[str, Any]) -> bool:
    if "retryable" in item:
        return bool(item.get("retryable"))
    priority = str(item.get("retry_priority") or "").lower()
    if priority in RETRYABLE_PRIORITIES:
        return True
    try:
        return int(item.get("response_status")) in RETRYABLE_STATUSES
    except (TypeError, ValueError):
        return False


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list_of_maps(value: Any) -> list[Mapping[str, Any]]:
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _int_or_zero(value: Any) -> int:
    return _int_or_none(value) or 0
