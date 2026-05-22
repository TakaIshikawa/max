"""Compact helpers for deterministic spec plan modules."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact
from max.spec._review_plan_common import row, unique_records


def named(value: Any, aliases: tuple[str, ...]) -> Any:
    if not isinstance(value, list):
        return value
    result = []
    for item in value:
        if isinstance(item, dict) and not compact(item.get("name")):
            item = {**item, "name": next((compact(item.get(key)) for key in aliases if compact(item.get(key))), "")}
        result.append(item)
    return result


def section(
    hints: dict[str, Any],
    keys: tuple[str, ...],
    prefix: str,
    owner: str,
    label: str,
    evidence_ids: list[str],
    fallback: list[Any],
    *,
    name_keys: tuple[str, ...] = ("name", "title", "id", "description"),
    extra_keys: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    value = next((hints[key] for key in keys if key in hints), None)
    return [
        item(prefix, index, record, owner, evidence_ids, label, name_keys=name_keys, extra_keys=extra_keys)
        for index, record in enumerate(unique_records(value, fallback), start=1)
    ]


def item(
    prefix: str,
    index: int,
    record: dict[str, Any],
    owner: str,
    evidence_ids: list[str],
    label: str,
    *,
    name_keys: tuple[str, ...] = ("name", "title", "id", "description"),
    extra_keys: tuple[str, ...] = (),
) -> dict[str, Any]:
    name = next((compact(record.get(key)) for key in name_keys if compact(record.get(key))), "")
    name = name or "unnamed item"
    description = (
        compact(record.get("description"))
        or compact(record.get("action"))
        or compact(record.get("justification"))
        or compact(record.get("details"))
        or f"{label}: {name}."
    )
    extras = {
        "severity": compact(record.get("severity")) or "medium",
        "status": compact(record.get("status")),
        "expiry": compact(record.get("expiry") or record.get("expiration")),
        "deadline": compact(record.get("deadline") or record.get("due")),
    }
    extras.update({key: compact(record.get(key)) for key in extra_keys})
    return row(
        prefix,
        index,
        name,
        compact(record.get("owner")) or owner,
        description,
        evidence_ids,
        **extras,
    )
