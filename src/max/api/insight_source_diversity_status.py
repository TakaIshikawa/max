"""JSON API renderer for insight source diversity status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.insight_source_diversity_status.v1"
KIND = "max.api.insight_source_diversity_status"


def insight_source_diversity_status_to_json(payload: Mapping[str, Any]) -> str:
    minimum = max(1, int_or_zero(payload.get("min_distinct_sources") or 2))
    warning_count = max(1, int_or_zero(payload.get("warning_low_diversity_count") or 1))
    critical_count = max(warning_count, int_or_zero(payload.get("critical_low_diversity_count") or 3))
    rows = [_row(item, index, minimum) for index, item in enumerate(_items(payload), start=1)]
    rows.sort(key=lambda row: (row["distinct_source_count"], row["insight_id"]))
    low_count = sum(1 for row in rows if row["low_diversity"])
    status = "critical" if low_count >= critical_count else "warning" if low_count >= warning_count else "ok"
    worst = next((row for row in rows if row["low_diversity"]), None)
    return json.dumps(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": KIND,
            "status": status,
            "min_distinct_sources": minimum,
            "insight_count": len(rows),
            "low_diversity_count": low_count,
            "worst_insight_id": worst["insight_id"] if worst else None,
            "insights": rows,
            "metadata": source_metadata(payload, insight_count=len(rows)),
        },
        indent=2,
        sort_keys=True,
    )


def _items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list_of_maps(payload.get("insights") or payload.get("items") or payload.get("rows"))


def _row(item: Mapping[str, Any], index: int, minimum: int) -> dict[str, Any]:
    explicit = item.get("distinct_source_count")
    source_count = max(0, int_or_zero(explicit)) if explicit is not None else len({_text(value) for value in (item.get("sources") if isinstance(item.get("sources"), list) else []) if _text(value)})
    return {
        "insight_id": _text(item.get("insight_id") or item.get("id")) or f"insight-{index}",
        "distinct_source_count": source_count,
        "low_diversity": source_count < minimum,
    }


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
