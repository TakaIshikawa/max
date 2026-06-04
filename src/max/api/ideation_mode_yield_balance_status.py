"""JSON API renderer for ideation mode yield balance status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.ideation_mode_yield_balance_status.v1"
KIND = "max.api.ideation_mode_yield_balance_status"
STATUS_RANK = {"critical": 0, "warning": 1, "insufficient_data": 2, "ok": 3}


def ideation_mode_yield_balance_status_to_json(payload: Mapping[str, Any], *, low_yield_threshold: float = 0.25, overrepresentation_threshold: float = 0.5) -> str:
    rows = [_row(item, index, low_yield_threshold, overrepresentation_threshold) for index, item in enumerate(_items(payload), start=1)]
    total_generated = sum(row["generated_count"] for row in rows)
    for row in rows:
        row["generation_share"] = round(row["generated_count"] / total_generated, 4) if total_generated else 0.0
        if row["status"] != "insufficient_data" and row["approval_rate"] < low_yield_threshold and row["generation_share"] >= overrepresentation_threshold:
            row["status"] = "critical"
    rows.sort(key=lambda row: (STATUS_RANK[row["status"]], row["approval_rate"], -row["generated_count"], row["mode"]))
    weakest = next((row for row in rows if row["status"] != "insufficient_data"), None)
    overall = "critical" if any(row["status"] == "critical" for row in rows) else "warning" if any(row["status"] == "warning" for row in rows) else "insufficient_data" if rows and all(row["status"] == "insufficient_data" for row in rows) else "ok"
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"mode_count": len(rows), "generated_count": total_generated, "approved_count": sum(row["approved_count"] for row in rows), "weakest_mode": weakest["mode"] if weakest else None, "status": overall, "recommendation": "rebalance generation away from low-yield modes" if overall in {"critical", "warning"} else "none"}, "mode_rows": rows, "metadata": source_metadata(payload, mode_count=len(rows))}, indent=2, sort_keys=True)


def _items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list_of_maps(payload.get("modes") or payload.get("rows") or payload.get("items"))


def _row(item: Mapping[str, Any], index: int, low: float, _over: float) -> dict[str, Any]:
    generated = max(0, int_or_zero(item.get("generated_count") or item.get("generated")))
    approved = max(0, int_or_zero(item.get("approved_count") or item.get("approved")))
    rate = approved / generated if generated else 0.0
    status = "insufficient_data" if generated == 0 else "warning" if rate < low else "ok"
    return {"mode": _text(item.get("mode") or item.get("ideation_mode")) or f"mode-{index}", "generated_count": generated, "approved_count": approved, "approval_rate": round(rate, 4), "generation_share": 0.0, "status": status}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
