"""JSON API renderer for source adapter cache staleness status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from max.api._renderer_utils import datetime_to_string, float_or_zero, int_or_zero, list_of_maps, mapping, parse_datetime, source_metadata

SCHEMA_VERSION = "max.api.source_adapter_cache_staleness_status.v1"
KIND = "max.api.source_adapter_cache_staleness_status"
STATUS_RANK = {"critical": 0, "warning": 1, "ok": 2}


def source_adapter_cache_staleness_status_to_json(
    payload: Any,
    *,
    as_of: datetime | str | None = None,
    warning_stale_hit_rate: float = 0.05,
    critical_stale_hit_rate: float = 0.2,
) -> str:
    payload_map = mapping(payload)
    as_of_dt = parse_datetime(as_of) or datetime.now(timezone.utc)
    adapters = _adapters(payload, as_of_dt, warning_stale_hit_rate, critical_stale_hit_rate)
    status = _overall_status(adapters)
    return json.dumps(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": KIND,
            "status": status,
            "summary": {
                "adapter_count": len(adapters),
                "stale_cache_count": sum(1 for row in adapters if row["status"] != "ok"),
                "total_stale_hit_count": sum(row["stale_hit_count"] for row in adapters),
                "max_stale_hit_rate": max((row["stale_hit_rate"] for row in adapters), default=0.0),
                "status": status,
            },
            "adapters": adapters,
            "metadata": source_metadata(payload_map, adapter_count=len(adapters)),
        },
        indent=2,
        sort_keys=True,
    )


def _adapters(payload: Any, as_of: datetime, warning_stale_hit_rate: float, critical_stale_hit_rate: float) -> list[dict[str, Any]]:
    payload_map = mapping(payload)
    source = payload_map.get("adapters") or payload_map.get("items") or (payload if isinstance(payload, list) else [])
    rows = [_adapter(row, index, as_of, warning_stale_hit_rate, critical_stale_hit_rate) for index, row in enumerate(list_of_maps(source), start=1)]
    return sorted(rows, key=lambda row: (STATUS_RANK[row["status"]], -row["stale_hit_rate"], -row["cache_age_minutes"], row["adapter"]))


def _adapter(item: Mapping[str, Any], index: int, as_of: datetime, warning_stale_hit_rate: float, critical_stale_hit_rate: float) -> dict[str, Any]:
    written = parse_datetime(item.get("cache_written_at"))
    age = max(0, int((as_of - written).total_seconds() // 60)) if written else 0
    ttl = max(0, int_or_zero(item.get("ttl_minutes")))
    hits = max(0, int_or_zero(item.get("hit_count")))
    stale_hits = max(0, int_or_zero(item.get("stale_hit_count")))
    stale_rate = round(stale_hits / hits, 4) if hits else 0.0
    if stale_rate > critical_stale_hit_rate:
        status = "critical"
    elif (ttl and age > ttl) or stale_rate > warning_stale_hit_rate:
        status = "warning"
    else:
        status = "ok"
    return {
        "adapter": _text(item.get("adapter") or item.get("source")) or f"adapter-{index}",
        "cache_key": _text(item.get("cache_key")) or None,
        "cache_written_at": datetime_to_string(written),
        "cache_age_minutes": age,
        "ttl_minutes": ttl,
        "hit_count": hits,
        "stale_hit_count": stale_hits,
        "stale_hit_rate": stale_rate,
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
