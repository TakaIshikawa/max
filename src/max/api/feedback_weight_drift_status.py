"""JSON API renderer for feedback weight drift status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from max.api._renderer_utils import datetime_to_string, float_or_zero, int_or_zero, source_metadata

SCHEMA_VERSION = "max.api.feedback_weight_drift_status.v1"
KIND = "max.api.feedback_weight_drift_status"


def feedback_weight_drift_status_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    dimensions = _dimensions(payload)
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(dimensions), "dimensions": dimensions, "drifted_dimensions": [row for row in dimensions if row["drifted"]], "metadata": source_metadata(payload, as_of=datetime_to_string(as_of) if isinstance(as_of, datetime) else as_of, dimension_count=len(dimensions))}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _dimensions(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("dimensions") if isinstance(payload.get("dimensions"), list) else payload.get("weights")
    rows = [_dimension(item, index, payload) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    return sorted(rows, key=lambda row: (-row["abs_delta"], row["dimension"]))


def _dimension(item: Mapping[str, Any], index: int, payload: Mapping[str, Any]) -> dict[str, Any]:
    baseline = float_or_zero(item.get("baseline_weight", item.get("baseline", item.get("previous_weight"))))
    current = float_or_zero(item.get("current_weight", item.get("current", item.get("weight"))))
    delta = round(current - baseline, 4)
    pct = round(delta / baseline, 4) if baseline else 0.0
    threshold = abs(float_or_zero(item.get("threshold", payload.get("threshold", 0.1))))
    return {"dimension": _bucket(item.get("dimension") or item.get("name"), f"dimension_{index}"), "baseline_weight": round(baseline, 4), "current_weight": round(current, 4), "delta": delta, "abs_delta": abs(delta), "percent_delta": pct, "approval_evidence_count": max(0, int_or_zero(item.get("approval_evidence_count", item.get("approvals")))), "rejection_evidence_count": max(0, int_or_zero(item.get("rejection_evidence_count", item.get("rejections")))), "drifted": abs(delta) >= threshold}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    drifted = sum(1 for row in rows if row["drifted"])
    max_delta = max((row["abs_delta"] for row in rows), default=0.0)
    return {"status": "drifting" if drifted else "stable", "dimension_count": len(rows), "drifted_dimension_count": drifted, "max_abs_delta": max_delta}


def _bucket(value: Any, default: str) -> str:
    return (_text(value) or default).lower().replace(" ", "_")


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
