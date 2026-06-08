"""JSON API renderer for budget stage spend status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import float_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.budget_stage_spend_status.v1"
KIND = "max.api.budget_stage_spend_status"
STATUS_RANK = {"critical": 0, "warning": 1, "healthy": 2}


def budget_stage_spend_status_to_json(payload: Mapping[str, Any], *, warning_threshold: float = 0.8, critical_threshold: float = 1.0) -> str:
    rows = [_row(item, warning_threshold, critical_threshold) for item in list_of_maps(payload.get("stages") or payload.get("rows") or payload.get("items"))]
    rows.sort(key=lambda row: (STATUS_RANK[row["status"]], row["stage"]))
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(rows), "stages": rows, "metadata": source_metadata(payload, stage_count=len(rows))}, indent=2, sort_keys=True)


def _row(item: Mapping[str, Any], warning: float, critical: float) -> dict[str, Any]:
    allocated = round(max(0.0, float_or_zero(item.get("allocated_amount", item.get("allocated")))), 2)
    actual = round(max(0.0, float_or_zero(item.get("actual_spend", item.get("spend")))), 2)
    percent = round(actual / allocated, 4) if allocated else (1.0 if actual else 0.0)
    status = "critical" if (allocated == 0 and actual > 0) or percent > critical else "warning" if percent >= warning else "healthy"
    return {"stage": _text(item.get("stage")) or "unknown", "allocated_amount": allocated, "actual_spend": actual, "variance": round(allocated - actual, 2), "percent_used": percent, "status": status}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"status": "critical" if any(row["status"] == "critical" for row in rows) else "warning" if any(row["status"] == "warning" for row in rows) else "healthy", "stage_count": len(rows), "total_allocated": round(sum(row["allocated_amount"] for row in rows), 2), "total_spend": round(sum(row["actual_spend"] for row in rows), 2)}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
