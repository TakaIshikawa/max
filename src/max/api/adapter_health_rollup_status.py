"""JSON API renderer for adapter health rollup status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from max.api._renderer_utils import float_or_zero, list_of_maps, parse_datetime, source_metadata

SCHEMA_VERSION = "max.api.adapter_health_rollup_status.v1"
KIND = "max.api.adapter_health_rollup_status"
RANK = {"critical": 0, "degraded": 1, "ok": 2}


def adapter_health_rollup_status_to_json(payload: Mapping[str, Any]) -> str:
    as_of = parse_datetime(payload.get("as_of")) or datetime.now(timezone.utc)
    stale_hours = float_or_zero(payload.get("stale_success_hours") or 24)
    rows = [_adapter(row, i, as_of, stale_hours) for i, row in enumerate(list_of_maps(payload.get("adapters") or payload.get("rows")), start=1)]
    unhealthy = [row for row in rows if row["status"] != "ok"]
    overall = "critical" if any(row["status"] == "critical" for row in rows) else ("degraded" if unhealthy else "ok")
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "overall_status": overall, "total_adapters": len(rows), "unhealthy_count": len(unhealthy), "stale_success_count": sum(1 for row in rows if row["stale_success"]), "unhealthy_adapters": sorted(unhealthy, key=lambda row: (RANK[row["status"]], row["adapter"].casefold())), "adapters": rows, "metadata": source_metadata(payload)}, indent=2, sort_keys=True)


def _adapter(item: Mapping[str, Any], index: int, as_of: datetime, stale_hours: float) -> dict[str, Any]:
    circuit = _text(item.get("circuit_state") or item.get("circuit") or "closed").casefold()
    availability = float_or_zero(item.get("availability") or item.get("availability_rate") or 1.0)
    error_rate = float_or_zero(item.get("recent_error_rate") or item.get("error_rate"))
    last_success = parse_datetime(item.get("last_successful_fetch_at") or item.get("last_success_at"))
    age_hours = round((as_of - last_success).total_seconds() / 3600, 2) if last_success else None
    stale = age_hours is None or age_hours > stale_hours
    status = "critical" if circuit == "open" or availability < 0.8 else ("degraded" if circuit in {"half_open", "half-open"} or error_rate >= 0.1 or stale else "ok")
    return {"adapter": _text(item.get("adapter") or item.get("name") or item.get("id")) or f"adapter-{index}", "availability": availability, "circuit_state": circuit, "recent_error_rate": error_rate, "last_successful_fetch_at": item.get("last_successful_fetch_at") or item.get("last_success_at"), "last_success_age_hours": age_hours, "stale_success": stale, "status": status}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
