"""JSON API renderer for feedback rejection reason taxonomy status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import float_or_zero, int_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.feedback_rejection_reason_taxonomy_status.v1"
KIND = "max.api.feedback_rejection_reason_taxonomy_status"
STATUS_RANK = {"critical": 0, "warning": 1, "ok": 2}


def feedback_rejection_reason_taxonomy_status_to_json(payload: Mapping[str, Any]) -> str:
    warning = _float(payload.get("warning_unmapped_rate"), 0.1)
    critical = _float(payload.get("critical_unmapped_rate"), 0.3)
    rows = sorted([_row(item, index, warning, critical) for index, item in enumerate(_items(payload), start=1)], key=lambda row: (STATUS_RANK[row["status"]], -row["unmapped_count"], row["profile"], row["reason"]))
    summary = _summary(rows)
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "status": summary["status"], "summary": summary, "reasons": rows, "metadata": source_metadata(payload, reason_count=len(rows))}, indent=2, sort_keys=True)


def _items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list_of_maps(payload.get("reasons") or payload.get("items") or payload.get("rows"))


def _row(item: Mapping[str, Any], index: int, warning: float, critical: float) -> dict[str, Any]:
    total = max(0, int_or_zero(item.get("rejection_count")))
    unmapped = max(0, int_or_zero(item.get("unmapped_count")))
    rate = round(unmapped / total, 4) if total else 0.0
    status = "critical" if rate >= critical else "warning" if rate >= warning else "ok"
    return {"profile": _text(item.get("profile")) or "unknown", "reason": _text(item.get("reason")) or f"reason-{index}", "rejection_count": total, "mapped_category": _text(item.get("mapped_category")) or "uncategorized", "unmapped_count": unmapped, "unmapped_rate": rate, "last_seen_at": _text(item.get("last_seen_at")), "status": status}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    critical = sum(1 for row in rows if row["status"] == "critical")
    warning = sum(1 for row in rows if row["status"] == "warning")
    return {"status": "critical" if critical else "warning" if warning else "ok", "reason_count": len(rows), "unmapped_reason_count": sum(1 for row in rows if row["unmapped_count"] > 0), "critical_count": critical, "warning_count": warning, "total_rejection_count": sum(row["rejection_count"] for row in rows), "total_unmapped_count": sum(row["unmapped_count"] for row in rows)}


def _float(value: Any, default: float) -> float:
    parsed = float_or_zero(value if value is not None else default)
    return parsed if parsed > 0 else default


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
