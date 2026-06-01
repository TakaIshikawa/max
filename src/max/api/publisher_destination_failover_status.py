"""JSON API renderer for publisher destination failover status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.publisher_destination_failover_status.v1"
KIND = "max.api.publisher_destination_failover_status"


def publisher_destination_failover_status_to_json(payload: Mapping[str, Any]) -> str:
    rows = [_destination(row, i) for i, row in enumerate(list_of_maps(payload.get("destinations") or payload.get("publishers") or payload.get("rows")), start=1)]
    missing = [row for row in rows if row["fallback_status"] != "healthy"]
    failed = sum(row["failover_failure_count"] for row in rows)
    status = "critical" if failed or any(row["status"] == "critical" for row in rows) else ("warning" if missing else "healthy")
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"destination_count": len(rows), "missing_fallback_count": len(missing), "failed_failover_count": failed, "status": status}, "destinations": rows, "destinations_without_healthy_fallback": sorted(missing, key=lambda row: (0 if row["status"] == "critical" else 1, row["destination"].casefold())), "metadata": source_metadata(payload)}, indent=2, sort_keys=True)


def _destination(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    success = int_or_zero(item.get("failover_success_count") or item.get("success_count"))
    failure = int_or_zero(item.get("failover_failure_count") or item.get("failure_count"))
    primary = _state(item.get("primary_status") or item.get("primary"))
    fallback = _state(item.get("fallback_status") or item.get("secondary_status") or item.get("secondary"))
    total = success + failure
    status = "healthy" if fallback == "healthy" and failure == 0 else ("critical" if primary != "healthy" and fallback != "healthy" else "warning")
    return {"destination": _text(item.get("destination") or item.get("publisher") or item.get("name")) or f"destination-{index}", "primary_status": primary, "fallback_status": fallback, "last_failover_at": item.get("last_failover_at"), "failover_success_count": success, "failover_failure_count": failure, "failover_success_rate": round(success / total, 4) if total else 1.0, "status": status}


def _state(value: Any) -> str:
    text = _text(value).casefold()
    return "healthy" if text in {"healthy", "ready", "ok", "true"} else ("unhealthy" if text in {"unhealthy", "failed", "down", "false"} else "unknown")


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
