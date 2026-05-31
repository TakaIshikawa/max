"""JSON API renderer for evaluation dimension coverage status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.evaluation_dimension_coverage_status.v1"
KIND = "max.api.evaluation_dimension_coverage_status"
DEFAULT_REQUIRED = ("impact", "confidence", "effort")


def evaluation_dimension_coverage_status_to_json(payload: Mapping[str, Any]) -> str:
    required = [str(item) for item in payload.get("required_dimensions", DEFAULT_REQUIRED)]
    rows = [_row(item, required) for item in list_of_maps(payload.get("evaluations") or payload.get("items"))]
    rows.sort(key=lambda row: (_rank(row["severity"]), row["unit_id"]))
    incomplete = [row for row in rows if row["severity"] != "ok"]
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"status": "incomplete" if incomplete else "complete", "evaluation_count": len(rows), "complete_count": len(rows) - len(incomplete), "incomplete_count": len(incomplete), "missing_dimension_count": sum(len(row["missing_dimensions"]) for row in rows)}, "rows": rows, "incomplete_evaluations": incomplete, "metadata": source_metadata(payload, required_dimensions=required)}, indent=2, sort_keys=True)


def _row(item: Mapping[str, Any], required: list[str]) -> dict[str, Any]:
    dimensions = item.get("dimensions") if isinstance(item.get("dimensions"), Mapping) else item
    present = sorted(str(name) for name in required if dimensions.get(name) is not None)
    missing = sorted(str(name) for name in required if dimensions.get(name) is None)
    ratio = round(len(present) / len(required), 4) if required else 1.0
    severity = "ok" if not missing else "warning" if present else "critical"
    return {"unit_id": str(item.get("unit_id") or item.get("buildable_unit_id") or item.get("id") or "unknown_unit"), "present_dimensions": present, "missing_dimensions": missing, "coverage_ratio": ratio, "severity": severity}


def _rank(value: str) -> int:
    return {"critical": 0, "warning": 1, "ok": 2}.get(value, 3)
