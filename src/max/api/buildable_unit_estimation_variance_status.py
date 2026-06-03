"""JSON API renderer for buildable unit estimation variance status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import float_or_zero, source_metadata

SCHEMA_VERSION = "max.api.buildable_unit_estimation_variance_status.v1"
KIND = "max.api.buildable_unit_estimation_variance_status"
STATUS_RANK = {"critical": 0, "warning": 1, "ok": 2, "insufficient_data": 3}


def buildable_unit_estimation_variance_status_to_json(payload: Mapping[str, Any], *, warning_ratio: float = 1.5, critical_ratio: float = 2.5) -> str:
    rows = _rows(payload, warning_ratio, critical_ratio)
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"total_units": len(rows), "underestimated_units": sum(1 for row in rows if row["variance_direction"] == "underestimated" and row["status"] in {"warning", "critical"}), "critical_units": sum(1 for row in rows if row["status"] == "critical"), "insufficient_data_units": sum(1 for row in rows if row["status"] == "insufficient_data")}, "unit_rows": rows, "metadata": source_metadata(payload, unit_count=len(rows))}, indent=2, sort_keys=True)


def _rows(payload: Mapping[str, Any], warning: float, critical: float) -> list[dict[str, Any]]:
    source = payload.get("units") or payload.get("items") or payload
    if isinstance(source, Mapping):
        items = [{**dict(value), "unit_id": value.get("unit_id") or key} for key, value in source.items() if isinstance(value, Mapping)]
    elif isinstance(source, list):
        items = [item for item in source if isinstance(item, Mapping)]
    else:
        items = []
    rows = [_row(item, index, warning, critical) for index, item in enumerate(items, start=1)]
    return sorted(rows, key=lambda row: (STATUS_RANK[row["status"]], -(row["variance_ratio"] or 0), row["unit_id"]))


def _row(item: Mapping[str, Any], index: int, warning: float, critical: float) -> dict[str, Any]:
    estimated = float_or_zero(item.get("estimated_effort_points", item.get("estimate")))
    actual_value = item.get("actual_effort_points", item.get("observed_effort_points"))
    actual = float_or_zero(actual_value)
    if estimated <= 0 or actual_value is None:
        ratio = None
        direction = "unknown"
        status = "insufficient_data"
    else:
        raw_ratio = actual / estimated
        direction = "underestimated" if actual > estimated else "overestimated" if actual < estimated else "matched"
        ratio = max(raw_ratio, 1 / raw_ratio) if raw_ratio > 0 else float("inf")
        status = "critical" if ratio >= critical else "warning" if ratio >= warning else "ok"
    return {"unit_id": _text(item.get("unit_id") or item.get("id")) or f"unit-{index}", "title": _text(item.get("title")) or None, "estimated_effort_points": round(estimated, 4), "actual_effort_points": round(actual, 4) if actual_value is not None else None, "variance_ratio": None if ratio is None or ratio == float("inf") else round(ratio, 4), "variance_direction": direction, "status": status}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
