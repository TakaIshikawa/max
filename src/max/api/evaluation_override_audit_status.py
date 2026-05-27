"""JSON API renderer for evaluation override audit status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import float_or_zero, source_metadata

SCHEMA_VERSION = "max.api.evaluation_override_audit_status.v1"
KIND = "max.api.evaluation_override_audit_status"


def evaluation_override_audit_status_to_json(payload: Mapping[str, Any]) -> str:
    rows = _rows(payload)
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(rows), "rows": rows, "audit_required_overrides": [row for row in rows if row["audit_required"]], "metadata": source_metadata(payload, override_count=len(rows))}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    threshold = max(0.0, float_or_zero(payload.get("audit_age_threshold_hours") or 72))
    source = payload.get("overrides") if isinstance(payload.get("overrides"), list) else payload.get("items")
    rows = [_row(item, threshold, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    return sorted(rows, key=lambda row: (not row["audit_required"], -row["age_hours"], row["idea_id"]))


def _row(item: Mapping[str, Any], threshold: float, index: int) -> dict[str, Any]:
    reason = _text(item.get("reason"))
    age = round(max(0.0, float_or_zero(item.get("age_hours"))), 4)
    stale = age > threshold
    audit_required = bool(not reason or stale)
    return {"idea_id": _text(item.get("idea_id")) or f"idea-{index}", "reviewer": _text(item.get("reviewer")) or "unknown-reviewer", "original_recommendation": _bucket(item.get("original_recommendation"), "unknown"), "override_recommendation": _bucket(item.get("override_recommendation"), "unknown"), "reason": reason or None, "reason_present": bool(reason), "age_hours": age, "audit_required": audit_required}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"status": "audit_required" if any(row["audit_required"] for row in rows) else "complete", "override_count": len(rows), "missing_reason_count": sum(1 for row in rows if not row["reason_present"]), "stale_count": sum(1 for row in rows if row["age_hours"] > 72), "audit_required_count": sum(1 for row in rows if row["audit_required"])}


def _bucket(value: Any, default: str) -> str:
    return (_text(value) or default).lower().replace(" ", "_")


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
