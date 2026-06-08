"""JSON API renderer for source API deprecation status."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from max.api._renderer_utils import bool_or_default, list_of_maps, parse_datetime, source_metadata, strings

SCHEMA_VERSION = "max.api.source_api_deprecation_status.v1"
KIND = "max.api.source_api_deprecation_status"
STATUS_RANK = {"urgent": 0, "watch": 1, "current": 2}


def source_api_deprecation_status_to_json(payload: Mapping[str, Any] | Sequence[Mapping[str, Any]], *, as_of: datetime | str | None = None, urgent_days: int = 30) -> str:
    now = parse_datetime(as_of) if as_of is not None else datetime.now(timezone.utc)
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for item in _items(payload):
        key = (_text(item.get("adapter")) or "unknown", _text(item.get("endpoint")) or "unknown")
        group = groups.setdefault(key, {"adapter": key[0], "endpoint": key[1], "deprecated_count": 0, "replacement_available": False, "profiles": set(), "sunset_at": None})
        group["profiles"].update(strings(item.get("profiles") or item.get("profile")))
        deprecated = bool_or_default(item.get("deprecated", item.get("is_deprecated")), default=False)
        if deprecated:
            group["deprecated_count"] += 1
        group["replacement_available"] = group["replacement_available"] or bool_or_default(item.get("replacement_available")) or bool(_text(item.get("replacement")))
        sunset = parse_datetime(item.get("sunset_at") or item.get("sunset_date"))
        if sunset is not None and (group["sunset_at"] is None or sunset < group["sunset_at"]):
            group["sunset_at"] = sunset
    rows = [_finish_group(group, now, urgent_days) for group in groups.values()]
    rows.sort(key=lambda row: (STATUS_RANK[row["status"]], row["adapter"], row["endpoint"]))
    metadata = source_metadata(payload if isinstance(payload, Mapping) else {}, group_count=len(rows))
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(rows), "endpoints": rows, "metadata": metadata}, indent=2, sort_keys=True)


def _finish_group(group: dict[str, Any], now: datetime, urgent_days: int) -> dict[str, Any]:
    sunset = group.pop("sunset_at")
    days = max((sunset.date() - now.date()).days, 0) if sunset is not None else None
    deprecated = group["deprecated_count"] > 0
    status = "urgent" if deprecated and (not group["replacement_available"] or (days is not None and days <= urgent_days)) else "watch" if deprecated else "current"
    return {**group, "impacted_profile_count": len(group["profiles"]), "profiles": sorted(group["profiles"]), "days_until_sunset": days, "status": status}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"status": "urgent" if any(row["status"] == "urgent" for row in rows) else "watch" if any(row["status"] == "watch" for row in rows) else "current", "endpoint_count": len(rows), "deprecated_count": sum(row["deprecated_count"] for row in rows), "urgent_count": sum(1 for row in rows if row["status"] == "urgent")}


def _items(payload: Mapping[str, Any] | Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    if isinstance(payload, Mapping):
        return list_of_maps(payload.get("endpoints") or payload.get("apis") or payload.get("rows") or payload.get("items"))
    return [item for item in payload if isinstance(item, Mapping)]


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
