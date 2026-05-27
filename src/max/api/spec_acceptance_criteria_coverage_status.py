"""JSON API renderer for spec acceptance criteria coverage status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import float_or_zero, int_or_zero, source_metadata

SCHEMA_VERSION = "max.api.spec_acceptance_criteria_coverage_status.v1"
KIND = "max.api.spec_acceptance_criteria_coverage_status"


def spec_acceptance_criteria_coverage_status_to_json(payload: Mapping[str, Any]) -> str:
    rows = _rows(payload)
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(rows), "rows": rows, "undercovered_specs": [row for row in rows if row["undercovered"]], "metadata": source_metadata(payload, spec_count=len(rows))}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("specs") if isinstance(payload.get("specs"), list) else payload.get("items")
    rows = [_row(item, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    return sorted(rows, key=lambda row: (not row["undercovered"], row["coverage_ratio"], row["spec_id"]))


def _row(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    criteria = max(0, int_or_zero(item.get("criteria_count")))
    testable = max(0, int_or_zero(item.get("testable_criteria_count")))
    untestable = max(0, int_or_zero(item.get("untestable_criteria_count", criteria - testable)))
    target = max(0.0, float_or_zero(item.get("target_coverage_ratio", 1.0)))
    ratio = round(testable / criteria, 4) if criteria else 1.0
    return {"spec_id": _text(item.get("spec_id")) or f"spec-{index}", "criteria_count": criteria, "testable_criteria_count": testable, "untestable_criteria_count": untestable, "coverage_ratio": ratio, "target_coverage_ratio": round(target, 4), "undercovered": bool(criteria and ratio < target)}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"status": "undercovered" if any(row["undercovered"] for row in rows) else "covered", "spec_count": len(rows), "total_criteria": sum(row["criteria_count"] for row in rows), "total_testable_criteria": sum(row["testable_criteria_count"] for row in rows), "undercovered_count": sum(1 for row in rows if row["undercovered"])}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
