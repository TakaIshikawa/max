"""JSON API renderer for feedback loop adaptation status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, source_metadata

SCHEMA_VERSION = "max.api.feedback_loop_adaptation_status.v1"
KIND = "max.api.feedback_loop_adaptation_status"


def feedback_loop_adaptation_status_to_json(payload: Mapping[str, Any]) -> str:
    rows = _rows(payload)
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(rows), "rows": rows, "metadata": source_metadata(payload, adaptation_count=len(rows))}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("adaptations") if isinstance(payload.get("adaptations"), list) else payload.get("items")
    rows = [_row(item) for item in source if isinstance(item, Mapping)] if isinstance(source, list) else []
    return sorted(rows, key=lambda row: (not row["backed_up"], row["profile"], row["outcome_label"]))


def _row(item: Mapping[str, Any]) -> dict[str, Any]:
    feedback = max(0, int_or_zero(item.get("feedback_count")))
    applied = max(0, int_or_zero(item.get("applied_adjustments")))
    pending = max(0, int_or_zero(item.get("pending_adjustments")))
    max_pending = max(0, int_or_zero(item.get("max_pending_adjustments")))
    return {"profile": _bucket(item.get("profile"), "default"), "outcome_label": _bucket(item.get("outcome_label"), "unknown"), "feedback_count": feedback, "applied_adjustments": applied, "pending_adjustments": pending, "last_applied_at": _text(item.get("last_applied_at")) or None, "max_pending_adjustments": max_pending, "applied_ratio": round(applied / feedback, 4) if feedback else 0.0, "backed_up": bool(max_pending and pending > max_pending)}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"status": "backed_up" if any(row["backed_up"] for row in rows) else "current", "total_feedback": sum(row["feedback_count"] for row in rows), "total_applied_adjustments": sum(row["applied_adjustments"] for row in rows), "total_pending_adjustments": sum(row["pending_adjustments"] for row in rows), "backed_up_count": sum(1 for row in rows if row["backed_up"])}


def _bucket(value: Any, default: str) -> str:
    return (_text(value) or default).lower().replace(" ", "_")


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
