"""JSON API renderer for publisher destination quota status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.publisher_destination_quota_status.v1"
KIND = "max.api.publisher_destination_quota_status"


def publisher_destination_quota_status_to_json(payload: Mapping[str, Any]) -> str:
    rows = [_destination(row, index) for index, row in enumerate(list_of_maps(payload.get("destinations") or payload.get("rows")), start=1)]
    rows.sort(key=lambda row: (row["remaining_quota_percentage"] if row["quota_limit"] is not None else 101.0, row["destination"]))
    warning = _float(payload.get("warning_remaining_percentage"), 0.2)
    critical = _float(payload.get("critical_remaining_percentage"), 0.05)
    exhausted = [row for row in rows if row["exhausted"]]
    low = [row for row in rows if not row["exhausted"] and row["quota_limit"] is not None and row["remaining_quota_percentage"] <= warning]
    required_exhausted = [row for row in exhausted if row["required"]]
    status = "critical" if required_exhausted or any(row["remaining_quota_percentage"] <= critical for row in rows if row["quota_limit"] is not None) else ("warning" if exhausted or low else "healthy")
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"status": status, "destination_count": len(rows), "exhausted_destination_count": len(exhausted), "low_quota_destination_count": len(low), "required_exhausted_count": len(required_exhausted)}, "destinations": rows, "exhausted_destinations": exhausted, "low_quota_destinations": low, "metadata": source_metadata(payload)}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _destination(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    unlimited = bool(item.get("unlimited")) or item.get("quota_limit") in (None, "unlimited")
    limit = None if unlimited else max(0, int_or_zero(item.get("quota_limit", item.get("limit"))))
    used = max(0, int_or_zero(item.get("used_quota", item.get("used"))))
    remaining = None if limit is None else max(limit - used, 0)
    pct = 1.0 if limit is None else (round(remaining / limit, 4) if limit else 0.0)
    rate = _float(item.get("usage_rate_per_hour"), 0.0)
    hours = round(remaining / rate, 2) if remaining is not None and rate > 0 else None
    return {"destination": _text(item.get("destination") or item.get("name") or f"destination-{index}"), "quota_limit": limit, "used_quota": used, "remaining_quota": remaining, "remaining_quota_percentage": pct, "projected_exhaustion_hours": hours, "reset_at": item.get("reset_at"), "required": bool(item.get("required", True)), "exhausted": limit is not None and remaining == 0}


def _float(value: Any, default: float) -> float:
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return default


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""

