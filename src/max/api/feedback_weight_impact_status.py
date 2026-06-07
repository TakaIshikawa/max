"""JSON API renderer for feedback-loop scoring weight impact status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import float_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.feedback_weight_impact_status.v1"
KIND = "max.api.feedback_weight_impact_status"


def feedback_weight_impact_status_to_json(payload: Mapping[str, Any]) -> str:
    threshold = _threshold(payload.get("material_delta_threshold"), 0.25)
    rows = [_row(item, index) for index, item in enumerate(_items(payload), start=1)]
    rows.sort(key=lambda row: (-abs(row["weight_delta"]), row["profile"], row["dimension"]))
    worst = rows[0] if rows else None
    largest_delta = abs(worst["weight_delta"]) if worst else 0.0
    status = "warning" if largest_delta >= threshold else "ok"
    return json.dumps(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": KIND,
            "status": status,
            "profile_count": len({row["profile"] for row in rows}),
            "dimension_count": len({row["dimension"] for row in rows}),
            "largest_delta": round(largest_delta, 4),
            "affected_profile": worst["profile"] if worst else None,
            "affected_dimension": worst["dimension"] if worst else None,
            "threshold": threshold,
            "weights": rows,
            "metadata": source_metadata(payload, weight_count=len(rows)),
        },
        indent=2,
        sort_keys=True,
    )


def _items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list_of_maps(payload.get("weights") or payload.get("dimensions") or payload.get("items") or payload.get("rows"))


def _row(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    before = float_or_zero(item.get("previous_weight") or item.get("before"))
    after = float_or_zero(item.get("current_weight") or item.get("after"))
    delta = item.get("weight_delta")
    parsed_delta = float_or_zero(delta) if delta is not None else after - before
    return {
        "profile": _text(item.get("profile") or item.get("profile_name")) or f"profile-{index}",
        "dimension": _text(item.get("dimension") or item.get("dimension_name")) or "unknown",
        "previous_weight": round(before, 4),
        "current_weight": round(after, 4),
        "weight_delta": round(parsed_delta, 4),
    }


def _threshold(value: Any, default: float) -> float:
    parsed = float_or_zero(value if value is not None else default)
    return parsed if parsed > 0 else default


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
