"""JSON API renderer for LLM budget reservation leak status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import float_or_zero, int_or_zero, list_of_maps, mapping, source_metadata

SCHEMA_VERSION = "max.api.llm_budget_reservation_leak_status.v1"
KIND = "max.api.llm_budget_reservation_leak_status"
STATUS_RANK = {"critical": 0, "warning": 1, "ok": 2}


def llm_budget_reservation_leak_status_to_json(
    payload: Any,
    *,
    critical_age_minutes: int = 60,
    warning_leak_ratio: float = 0.1,
) -> str:
    payload_map = mapping(payload)
    reservations = _reservations(payload, critical_age_minutes=critical_age_minutes, warning_leak_ratio=warning_leak_ratio)
    status = _overall_status(reservations)
    return json.dumps(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": KIND,
            "status": status,
            "summary": {
                "reservation_count": len(reservations),
                "leaking_reservation_count": sum(1 for row in reservations if row["unreleased_tokens"] > 0),
                "total_unreleased_tokens": sum(row["unreleased_tokens"] for row in reservations),
                "max_leak_ratio": max((row["leak_ratio"] for row in reservations), default=0.0),
                "status": status,
            },
            "reservations": reservations,
            "metadata": source_metadata(payload_map, reservation_count=len(reservations)),
        },
        indent=2,
        sort_keys=True,
    )


def _reservations(payload: Any, *, critical_age_minutes: int, warning_leak_ratio: float) -> list[dict[str, Any]]:
    payload_map = mapping(payload)
    source = payload_map.get("reservations") or payload_map.get("items") or (payload if isinstance(payload, list) else [])
    rows = [_reservation(row, index, critical_age_minutes, warning_leak_ratio) for index, row in enumerate(list_of_maps(source), start=1)]
    return sorted(rows, key=lambda row: (STATUS_RANK[row["status"]], -row["unreleased_tokens"], row["reservation_id"]))


def _reservation(item: Mapping[str, Any], index: int, critical_age_minutes: int, warning_leak_ratio: float) -> dict[str, Any]:
    reserved = max(0, int_or_zero(item.get("reserved_tokens")))
    consumed = max(0, int_or_zero(item.get("consumed_tokens")))
    released = max(0, int_or_zero(item.get("released_tokens")))
    unreleased = max(0, reserved - consumed - released)
    leak_ratio = round(unreleased / reserved, 4) if reserved else 0.0
    age = max(0.0, float_or_zero(item.get("age_minutes")))
    if unreleased and age > critical_age_minutes:
        status = "critical"
    elif leak_ratio > warning_leak_ratio:
        status = "warning"
    else:
        status = "ok"
    return {
        "reservation_id": _text(item.get("reservation_id") or item.get("id")) or f"reservation-{index}",
        "profile": _text(item.get("profile")) or "default",
        "reserved_tokens": reserved,
        "consumed_tokens": consumed,
        "released_tokens": released,
        "unreleased_tokens": unreleased,
        "leak_ratio": leak_ratio,
        "age_minutes": age,
        "state": _text(item.get("state")) or "unknown",
        "status": status,
    }


def _overall_status(rows: list[dict[str, Any]]) -> str:
    if any(row["status"] == "critical" for row in rows):
        return "critical"
    if any(row["status"] == "warning" for row in rows):
        return "warning"
    return "ok"


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
