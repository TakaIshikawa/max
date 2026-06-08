"""JSON API renderer for budget reservation utilization status."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from max.api._renderer_utils import bool_or_default, float_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.budget_reservation_utilization_status.v1"
KIND = "max.api.budget_reservation_utilization_status"
STATUS_RANK = {"exhausted": 0, "underused": 1, "efficient": 2}


def budget_reservation_utilization_status_to_json(
    payload: Mapping[str, Any] | Sequence[Mapping[str, Any]],
    *,
    underused_threshold: float = 50.0,
    exhausted_threshold: float = 95.0,
) -> str:
    reservations = _items(payload)
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for item in reservations:
        key = (_text(item.get("profile")) or "default", _text(item.get("stage") or item.get("pipeline_stage")) or "unknown")
        group = groups.setdefault(key, {"profile": key[0], "pipeline_stage": key[1], "reserved_amount": 0.0, "consumed_amount": 0.0, "expired_reservation_count": 0})
        group["reserved_amount"] += max(0.0, float_or_zero(item.get("reserved_amount", item.get("reserved"))))
        group["consumed_amount"] += max(0.0, float_or_zero(item.get("consumed_amount", item.get("consumed"))))
        if bool_or_default(item.get("expired", item.get("is_expired")), default=False):
            group["expired_reservation_count"] += 1

    rows = [_finish_group(group, underused_threshold, exhausted_threshold) for group in groups.values()]
    rows.sort(key=lambda row: (STATUS_RANK[row["status"]], row["profile"], row["pipeline_stage"]))
    summary = _summary(rows)
    metadata = source_metadata(payload if isinstance(payload, Mapping) else {}, group_count=len(rows))
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": summary, "reservations": rows, "metadata": metadata}, indent=2, sort_keys=True)


def _finish_group(group: dict[str, Any], underused_threshold: float, exhausted_threshold: float) -> dict[str, Any]:
    reserved = round(group["reserved_amount"], 2)
    consumed = min(round(group["consumed_amount"], 2), reserved) if reserved else 0.0
    unused = round(max(reserved - consumed, 0.0), 2)
    utilization = round((consumed / reserved) * 100, 2) if reserved else 0.0
    status = "exhausted" if reserved and utilization >= exhausted_threshold else "underused" if reserved and utilization < underused_threshold else "efficient"
    return {**group, "reserved_amount": reserved, "consumed_amount": consumed, "unused_amount": unused, "utilization_percent": utilization, "status": status}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    reserved = round(sum(row["reserved_amount"] for row in rows), 2)
    consumed = round(sum(row["consumed_amount"] for row in rows), 2)
    return {
        "status": "exhausted" if any(row["status"] == "exhausted" for row in rows) else "underused" if any(row["status"] == "underused" for row in rows) else "efficient",
        "group_count": len(rows),
        "reserved_amount": reserved,
        "consumed_amount": consumed,
        "unused_amount": round(max(reserved - consumed, 0.0), 2),
        "utilization_percent": round((consumed / reserved) * 100, 2) if reserved else 0.0,
        "expired_reservation_count": sum(row["expired_reservation_count"] for row in rows),
    }


def _items(payload: Mapping[str, Any] | Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    if isinstance(payload, Mapping):
        return list_of_maps(payload.get("reservations") or payload.get("rows") or payload.get("items"))
    return [item for item in payload if isinstance(item, Mapping)]


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
