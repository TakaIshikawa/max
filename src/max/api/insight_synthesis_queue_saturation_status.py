"""JSON API renderer for insight synthesis queue saturation status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import float_or_zero, int_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.insight_synthesis_queue_saturation_status.v1"
KIND = "max.api.insight_synthesis_queue_saturation_status"
STATUS_RANK = {"critical": 0, "warning": 1, "ok": 2}


def insight_synthesis_queue_saturation_status_to_json(payload: Mapping[str, Any]) -> str:
    warning_ratio = _float(payload.get("warning_saturation_ratio"), 0.7)
    critical_ratio = _float(payload.get("critical_saturation_ratio"), 1.0)
    warning_age = _float(payload.get("warning_age_minutes"), 120.0)
    critical_age = _float(payload.get("critical_age_minutes"), 240.0)
    rows = sorted([_row(item, index, warning_ratio, critical_ratio, warning_age, critical_age) for index, item in enumerate(_items(payload), start=1)], key=lambda row: (STATUS_RANK[row["status"]], -row["oldest_pending_age_minutes"], row["profile"]))
    summary = _summary(rows)
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "status": summary["status"], "summary": summary, "queues": rows, "metadata": source_metadata(payload, profile_count=len(rows))}, indent=2, sort_keys=True)


def _items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list_of_maps(payload.get("queues") or payload.get("items") or payload.get("rows"))


def _row(item: Mapping[str, Any], index: int, wr: float, cr: float, wa: float, ca: float) -> dict[str, Any]:
    pending = max(0, int_or_zero(item.get("pending_signal_count")))
    capacity = max(0, int_or_zero(item.get("batch_capacity")))
    ratio = round(pending / capacity, 4) if capacity else 0.0
    age = max(0.0, float_or_zero(item.get("oldest_pending_age_minutes")))
    if ratio >= cr or age >= ca:
        status = "critical"
    elif ratio >= wr or age >= wa:
        status = "warning"
    else:
        status = "ok"
    return {"profile": _text(item.get("profile")) or f"profile-{index}", "pending_signal_count": pending, "in_flight_batch_count": max(0, int_or_zero(item.get("in_flight_batch_count"))), "batch_capacity": capacity, "saturation_ratio": ratio, "oldest_pending_age_minutes": age, "age_minutes": age, "failed_batch_count": max(0, int_or_zero(item.get("failed_batch_count"))), "status": status}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    critical = sum(1 for row in rows if row["status"] == "critical")
    warning = sum(1 for row in rows if row["status"] == "warning")
    return {"status": "critical" if critical else "warning" if warning else "ok", "profile_count": len(rows), "saturated_profile_count": critical + warning, "critical_count": critical, "warning_count": warning, "total_pending_signal_count": sum(row["pending_signal_count"] for row in rows), "oldest_pending_age_minutes": max((row["oldest_pending_age_minutes"] for row in rows), default=0.0)}


def _float(value: Any, default: float) -> float:
    parsed = float_or_zero(value if value is not None else default)
    return parsed if parsed > 0 else default


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
