"""JSON API renderer for feedback learning weight saturation status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import float_or_zero, int_or_zero, list_of_maps, mapping, source_metadata

SCHEMA_VERSION = "max.api.feedback_learning_weight_saturation_status.v1"
KIND = "max.api.feedback_learning_weight_saturation_status"
STATUS_RANK = {"critical": 0, "warning": 1, "ok": 2}


def feedback_learning_weight_saturation_status_to_json(payload: Any, *, warning_saturation_ratio: float = 0.8) -> str:
    payload_map = mapping(payload)
    dimensions = _dimensions(payload, warning_saturation_ratio)
    status = _overall_status(dimensions)
    return json.dumps(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": KIND,
            "status": status,
            "summary": {
                "dimension_count": len(dimensions),
                "saturated_dimension_count": sum(1 for row in dimensions if row["status"] == "critical"),
                "max_saturation_ratio": max((row["saturation_ratio"] for row in dimensions), default=0.0),
                "total_adjustment_count": sum(row["adjustment_count"] for row in dimensions),
                "status": status,
            },
            "dimensions": dimensions,
            "metadata": source_metadata(payload_map, dimension_count=len(dimensions)),
        },
        indent=2,
        sort_keys=True,
    )


def _dimensions(payload: Any, warning_saturation_ratio: float) -> list[dict[str, Any]]:
    payload_map = mapping(payload)
    source = payload_map.get("dimensions") or payload_map.get("items") or (payload if isinstance(payload, list) else [])
    rows = [_dimension(row, index, warning_saturation_ratio) for index, row in enumerate(list_of_maps(source), start=1)]
    return sorted(rows, key=lambda row: (STATUS_RANK[row["status"]], -row["saturation_ratio"], row["dimension"]))


def _dimension(item: Mapping[str, Any], index: int, warning_saturation_ratio: float) -> dict[str, Any]:
    current = float_or_zero(item.get("current_weight"))
    minimum = float_or_zero(item.get("min_weight"))
    maximum = float_or_zero(item.get("max_weight"))
    span = maximum - minimum
    if span <= 0:
        saturation = 1.0
    else:
        midpoint = minimum + span / 2
        saturation = min(1.0, round(abs(current - midpoint) / (span / 2), 4))
    if span <= 0 or current <= minimum or current >= maximum:
        status = "critical"
    elif saturation > warning_saturation_ratio:
        status = "warning"
    else:
        status = "ok"
    return {
        "dimension": _text(item.get("dimension") or item.get("name")) or f"dimension-{index}",
        "current_weight": current,
        "min_weight": minimum,
        "max_weight": maximum,
        "saturation_ratio": saturation,
        "adjustment_count": max(0, int_or_zero(item.get("adjustment_count"))),
        "last_adjusted_at": item.get("last_adjusted_at"),
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
