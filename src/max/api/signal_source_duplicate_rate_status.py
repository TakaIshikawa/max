"""JSON API renderer for signal source duplicate-rate status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import float_or_zero, int_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.signal_source_duplicate_rate_status.v1"
KIND = "max.api.signal_source_duplicate_rate_status"


def signal_source_duplicate_rate_status_to_json(payload: Mapping[str, Any]) -> str:
    warning = _threshold(payload.get("warning_duplicate_rate"), 0.1)
    critical = _threshold(payload.get("critical_duplicate_rate"), 0.25)
    rows = [_row(item, index) for index, item in enumerate(_items(payload), start=1)]
    rows.sort(key=lambda row: (-row["duplicate_rate"], row["source"]))
    worst = rows[0] if rows else None
    duplicate_rate = worst["duplicate_rate"] if worst else 0.0
    status = "critical" if duplicate_rate >= critical else "warning" if duplicate_rate >= warning else "ok"
    return json.dumps(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": KIND,
            "status": status,
            "threshold": warning,
            "critical_threshold": critical,
            "worst_source": worst["source"] if worst else None,
            "duplicate_rate": duplicate_rate,
            "source_count": len(rows),
            "sources": rows,
            "metadata": source_metadata(payload, source_count=len(rows)),
        },
        indent=2,
        sort_keys=True,
    )


def _items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list_of_maps(payload.get("sources") or payload.get("items") or payload.get("rows"))


def _row(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    total = max(0, int_or_zero(item.get("signal_count") or item.get("total_count")))
    dupes = max(0, int_or_zero(item.get("duplicate_count")))
    rate = item.get("duplicate_rate")
    parsed_rate = max(0.0, float_or_zero(rate)) if rate is not None else (dupes / total if total else 0.0)
    return {"source": _text(item.get("source") or item.get("source_id")) or f"source-{index}", "signal_count": total, "duplicate_count": dupes, "duplicate_rate": round(parsed_rate, 4)}


def _threshold(value: Any, default: float) -> float:
    parsed = float_or_zero(value if value is not None else default)
    return parsed if parsed > 0 else default


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
