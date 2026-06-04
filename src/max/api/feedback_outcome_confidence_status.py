"""JSON API renderer for feedback outcome confidence status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.feedback_outcome_confidence_status.v1"
KIND = "max.api.feedback_outcome_confidence_status"
STATUS_RANK = {"ambiguous": 0, "low_confidence": 1, "insufficient_data": 2, "high_confidence": 3}


def feedback_outcome_confidence_status_to_json(payload: Mapping[str, Any], *, confidence_threshold: float = 0.7) -> str:
    rows = [_row(item, index, confidence_threshold) for index, item in enumerate(_items(payload), start=1)]
    rows.sort(key=lambda row: (STATUS_RANK[row["status"]], row["confidence_ratio"], row["profile"], row["idea_id"]))
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"record_count": len(rows), "high_confidence_count": sum(1 for row in rows if row["status"] == "high_confidence"), "ambiguous_count": sum(1 for row in rows if row["status"] == "ambiguous"), "insufficient_data_count": sum(1 for row in rows if row["status"] == "insufficient_data")}, "outcome_rows": rows, "metadata": source_metadata(payload, record_count=len(rows))}, indent=2, sort_keys=True)


def _items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list_of_maps(payload.get("outcomes") or payload.get("rows") or payload.get("items"))


def _row(item: Mapping[str, Any], index: int, threshold: float) -> dict[str, Any]:
    approvals = _count(item.get("approval_count") or item.get("approvals"))
    rejections = _count(item.get("rejection_count") or item.get("rejections"))
    reversals = _count(item.get("reversal_count") or item.get("reversals"))
    low = _count(item.get("low_confidence_count") or item.get("low_confidence_labels"))
    total = approvals + rejections
    winner = max(approvals, rejections)
    ratio = winner / total if total else 0.0
    status = "insufficient_data" if total == 0 else "ambiguous" if reversals or (approvals and rejections and ratio < threshold) else "low_confidence" if low / total >= 0.5 else "high_confidence"
    return {"idea_id": _text(item.get("idea_id") or item.get("id")) or f"idea-{index}", "profile": _text(item.get("profile")) or "default", "approval_count": approvals, "rejection_count": rejections, "reversal_count": reversals, "low_confidence_count": low, "confidence_ratio": round(ratio, 4), "status": status}


def _count(value: Any) -> int:
    return max(0, int_or_zero(value))


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
