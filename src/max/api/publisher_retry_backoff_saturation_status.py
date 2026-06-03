"""JSON API renderer for publisher retry backoff saturation status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import float_or_zero, int_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.publisher_retry_backoff_saturation_status.v1"
KIND = "max.api.publisher_retry_backoff_saturation_status"
STATUS_RANK = {"critical": 0, "warning": 1, "ok": 2}


def publisher_retry_backoff_saturation_status_to_json(payload: Mapping[str, Any]) -> str:
    warning = _float(payload.get("warning_backoff_ratio"), 0.7)
    critical = _float(payload.get("critical_backoff_ratio"), 0.9)
    rows = sorted([_row(item, index, warning, critical) for index, item in enumerate(_items(payload), start=1)], key=lambda row: (STATUS_RANK[row["status"]], -row["oldest_retry_age_minutes"], row["destination"]))
    summary = _summary(rows)
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "status": summary["status"], "summary": summary, "destinations": rows, "metadata": source_metadata(payload, destination_count=len(rows))}, indent=2, sort_keys=True)


def _items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list_of_maps(payload.get("destinations") or payload.get("items") or payload.get("rows"))


def _row(item: Mapping[str, Any], index: int, warning: float, critical: float) -> dict[str, Any]:
    current = max(0.0, float_or_zero(item.get("current_retry_delay_seconds")))
    maximum = max(0.0, float_or_zero(item.get("max_retry_delay_seconds")))
    ratio = round(current / maximum, 4) if maximum else 0.0
    budget = max(0, int_or_zero(item.get("retry_budget_remaining")))
    status = "critical" if budget <= 0 or ratio >= critical else "warning" if ratio >= warning else "ok"
    return {"destination": _text(item.get("destination")) or f"destination-{index}", "queued_retry_count": max(0, int_or_zero(item.get("queued_retry_count"))), "max_retry_delay_seconds": maximum, "current_retry_delay_seconds": current, "backoff_ratio": ratio, "retry_budget_remaining": budget, "oldest_retry_age_minutes": max(0.0, float_or_zero(item.get("oldest_retry_age_minutes"))), "status": status}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    critical = sum(1 for row in rows if row["status"] == "critical")
    warning = sum(1 for row in rows if row["status"] == "warning")
    return {"status": "critical" if critical else "warning" if warning else "ok", "destination_count": len(rows), "saturated_destination_count": critical + warning, "critical_count": critical, "warning_count": warning, "total_queued_retry_count": sum(row["queued_retry_count"] for row in rows), "max_backoff_ratio": max((row["backoff_ratio"] for row in rows), default=0.0)}


def _float(value: Any, default: float) -> float:
    parsed = float_or_zero(value if value is not None else default)
    return parsed if parsed > 0 else default


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
