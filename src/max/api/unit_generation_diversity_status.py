"""JSON API renderer for unit generation diversity status."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import float_or_zero, int_or_zero, source_metadata

SCHEMA_VERSION = "max.api.unit_generation_diversity_status.v1"
KIND = "max.api.unit_generation_diversity_status"


def unit_generation_diversity_status_to_json(payload: Mapping[str, Any]) -> str:
    rows = _rows(payload)
    total = sum(row["unit_count"] for row in rows)
    rows = [{**row, "share_ratio": round(row["unit_count"] / total, 4) if total else 0.0} for row in rows]
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(rows, total), "rows": sorted(rows, key=lambda row: (-row["share_ratio"], row["stack"], row["mode"], row["profile"])), "metadata": source_metadata(payload, segment_count=len(rows))}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("segments") if isinstance(payload.get("segments"), list) else payload.get("items")
    return [_row(item) for item in source if isinstance(item, Mapping)] if isinstance(source, list) else []


def _row(item: Mapping[str, Any]) -> dict[str, Any]:
    return {"profile": _bucket(item.get("profile"), "default"), "mode": _bucket(item.get("mode"), "unknown"), "stack": _bucket(item.get("stack"), "unknown"), "target_user": _bucket(item.get("target_user"), "general"), "unit_count": max(0, int_or_zero(item.get("unit_count"))), "minimum_share_ratio": round(max(0.0, float_or_zero(item.get("minimum_share_ratio"))), 4)}


def _summary(rows: list[dict[str, Any]], total: int) -> dict[str, Any]:
    dominant = []
    for field in ("stack", "mode"):
        counts = Counter()
        thresholds = {}
        for row in rows:
            counts[row[field]] += row["unit_count"]
            thresholds[row[field]] = max(thresholds.get(row[field], 0.0), row["minimum_share_ratio"])
        dominant.extend({"segment_type": field, "segment": key, "share_ratio": round(count / total, 4)} for key, count in counts.items() if total and count / total > thresholds[key])
    return {"status": "concentrated" if dominant else "diverse", "total_units": total, "distinct_stack_count": len({row["stack"] for row in rows}), "distinct_mode_count": len({row["mode"] for row in rows}), "dominant_segments": sorted(dominant, key=lambda row: (row["segment_type"], row["segment"]))}


def _bucket(value: Any, default: str) -> str:
    text = " ".join(str(value).strip().split()) if value is not None else ""
    return (text or default).lower().replace(" ", "_")
