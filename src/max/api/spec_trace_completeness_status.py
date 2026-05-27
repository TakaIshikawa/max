"""JSON API renderer for spec trace completeness status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, source_metadata

SCHEMA_VERSION = "max.api.spec_trace_completeness_status.v1"
KIND = "max.api.spec_trace_completeness_status"


def spec_trace_completeness_status_to_json(payload: Mapping[str, Any]) -> str:
    rows = _rows(payload)
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(rows), "rows": rows, "incomplete_specs": [row for row in rows if row["incomplete"]], "metadata": source_metadata(payload, spec_count=len(rows))}, indent=2, sort_keys=True)


def _rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("specs") if isinstance(payload.get("specs"), list) else payload.get("items")
    rows = [_row(item, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    return sorted(rows, key=lambda row: (not row["incomplete"], -row["missing_trace_count"], row["spec_id"]))


def _row(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    signal_count = max(0, int_or_zero(item.get("signal_count")))
    required = max(0, int_or_zero(item.get("required_signal_count")))
    missing = max(0, int_or_zero(item.get("missing_trace_count")))
    incomplete = signal_count < required or missing > 0
    return {"spec_id": _text(item.get("spec_id")) or f"spec-{index}", "unit_id": _text(item.get("unit_id")) or "unknown-unit", "insight_count": max(0, int_or_zero(item.get("insight_count"))), "signal_count": signal_count, "required_signal_count": required, "missing_trace_count": missing, "incomplete": incomplete}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    incomplete_count = sum(1 for row in rows if row["incomplete"])
    return {"status": "incomplete" if incomplete_count else "complete", "spec_count": len(rows), "incomplete_count": incomplete_count, "total_missing_trace_count": sum(row["missing_trace_count"] for row in rows)}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
