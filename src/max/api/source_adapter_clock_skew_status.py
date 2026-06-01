"""JSON API renderer for source adapter clock skew status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import float_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.source_adapter_clock_skew_status.v1"
KIND = "max.api.source_adapter_clock_skew_status"
RANK = {"critical": 0, "warning": 1, "unknown": 2, "healthy": 3}


def source_adapter_clock_skew_status_to_json(payload: Mapping[str, Any]) -> str:
    rows = [_row(item, index) for index, item in enumerate(_items(payload), start=1)]
    rows.sort(key=lambda row: (RANK[row["status"]], row["adapter"], row["source"]))
    affected = [row for row in rows if row["status"] in {"critical", "warning", "unknown"}]
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "status": _overall(rows),
            "adapter_count": len(rows),
            "affected_adapter_count": len(affected),
            "critical_count": sum(1 for row in rows if row["status"] == "critical"),
            "warning_count": sum(1 for row in rows if row["status"] == "warning"),
            "unknown_count": sum(1 for row in rows if row["status"] == "unknown"),
        },
        "affected_adapters": affected,
        "adapters": rows,
        "actions": _actions(affected),
        "metadata": source_metadata(payload),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list_of_maps(payload.get("adapters") or payload.get("rows") or payload.get("clock_skews"))


def _row(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    adapter = str(item.get("adapter") or item.get("adapter_id") or item.get("adapter_name") or f"adapter-{index}")
    source = str(item.get("source") or item.get("source_id") or item.get("source_name") or "unknown")
    skew = item.get("skew_seconds")
    tolerance = item.get("tolerance_seconds")
    missing = [
        key
        for key in ("observed_at", "source_time", "system_time")
        if item.get(key) in (None, "")
    ]
    if skew in (None, ""):
        missing.append("skew_seconds")
    if tolerance in (None, ""):
        missing.append("tolerance_seconds")
    skew_value = float_or_zero(skew)
    tolerance_value = float_or_zero(tolerance)
    status = _status(skew_value, tolerance_value, missing)
    return {
        "adapter": adapter,
        "source": source,
        "observed_at": item.get("observed_at"),
        "source_time": item.get("source_time"),
        "system_time": item.get("system_time"),
        "skew_seconds": round(skew_value, 3) if skew not in (None, "") else None,
        "tolerance_seconds": round(tolerance_value, 3) if tolerance not in (None, "") else None,
        "status": status,
        "missing_fields": sorted(set(missing)),
        "action": _action(status),
    }


def _status(skew: float, tolerance: float, missing: list[str]) -> str:
    if missing or tolerance <= 0:
        return "unknown"
    ratio = abs(skew) / tolerance
    if ratio >= 2:
        return "critical"
    if ratio > 1:
        return "warning"
    return "healthy"


def _overall(rows: list[dict[str, Any]]) -> str:
    for status in ("critical", "warning", "unknown"):
        if any(row["status"] == status for row in rows):
            return status
    return "healthy"


def _action(status: str) -> str:
    return {
        "critical": "pause incremental fetches and synchronize adapter host clocks",
        "warning": "verify NTP synchronization before the next scheduled fetch",
        "unknown": "record observed_at, source_time, system_time, skew_seconds, and tolerance_seconds",
    }.get(status, "none")


def _actions(rows: list[dict[str, Any]]) -> list[str]:
    return sorted({_action(row["status"]) for row in rows if row["status"] != "healthy"})
