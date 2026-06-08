"""JSON API renderer for publisher delivery success rate status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.publisher_delivery_success_rate_status.v1"
KIND = "max.api.publisher_delivery_success_rate_status"
STATUS_RANK = {"critical": 0, "degraded": 1, "healthy": 2}


def publisher_delivery_success_rate_status_to_json(payload: Mapping[str, Any], *, degraded_threshold: float = 0.95, critical_threshold: float = 0.8) -> str:
    rows = [_row(item, degraded_threshold, critical_threshold) for item in list_of_maps(payload.get("destinations") or payload.get("channels") or payload.get("rows") or payload.get("items"))]
    rows.sort(key=lambda row: (row["destination"], row["channel"]))
    delivered = sum(row["delivered_count"] for row in rows)
    failed = sum(row["failed_count"] for row in rows)
    total = delivered + failed
    success_rate = round(delivered / total, 4) if total else 1.0
    status = "critical" if any(row["status"] == "critical" for row in rows) else "degraded" if any(row["status"] == "degraded" for row in rows) else "healthy"
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"status": status, "destination_count": len(rows), "delivered_count": delivered, "failed_count": failed, "success_rate": success_rate}, "destinations": rows, "metadata": source_metadata(payload, destination_count=len(rows))}, indent=2, sort_keys=True)


def _row(item: Mapping[str, Any], degraded: float, critical: float) -> dict[str, Any]:
    delivered = max(0, int_or_zero(item.get("delivered_count", item.get("delivered"))))
    failed = max(0, int_or_zero(item.get("failed_count", item.get("failed"))))
    total = delivered + failed
    rate = round(delivered / total, 4) if total else 1.0
    status = "critical" if total and rate < critical else "degraded" if total and rate < degraded else "healthy"
    return {"destination": _text(item.get("destination")) or "unknown", "channel": _text(item.get("channel")) or "default", "total_count": total, "delivered_count": delivered, "failed_count": failed, "success_rate": rate, "status": status}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
