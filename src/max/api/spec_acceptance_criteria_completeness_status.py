"""JSON API renderer for spec acceptance criteria completeness status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import as_list, int_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.spec_acceptance_criteria_completeness_status.v1"
KIND = "max.api.spec_acceptance_criteria_completeness_status"
STATUS_RANK = {"incomplete": 0, "complete": 1}


def spec_acceptance_criteria_completeness_status_to_json(payload: Mapping[str, Any], *, completeness_threshold: float = 1.0) -> str:
    rows = [_row(item, index, completeness_threshold) for index, item in enumerate(list_of_maps(payload.get("specs") or payload.get("rows") or payload.get("items")), start=1)]
    rows.sort(key=lambda row: (STATUS_RANK[row["status"]], row["spec_id"]))
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"status": "incomplete" if any(row["status"] == "incomplete" for row in rows) else "complete", "spec_count": len(rows), "incomplete_count": sum(1 for row in rows if row["status"] == "incomplete")}, "specs": rows, "metadata": source_metadata(payload, spec_count=len(rows))}, indent=2, sort_keys=True)


def _row(item: Mapping[str, Any], index: int, threshold: float) -> dict[str, Any]:
    required = max(0, int_or_zero(item.get("required_criteria_count", item.get("required_count"))))
    present = max(0, int_or_zero(item.get("present_criteria_count", item.get("present_count"))))
    if not present:
        present = len([criterion for criterion in as_list(item.get("criteria")) if _text(criterion)])
    ratio = round(present / required, 4) if required else (1.0 if present == 0 else 0.0)
    return {"spec_id": _text(item.get("spec_id") or item.get("id")) or f"spec-{index}", "unit_id": _text(item.get("unit_id")) or "unknown", "required_criteria_count": required, "present_criteria_count": present, "missing_categories": [_text(category) for category in as_list(item.get("missing_categories")) if _text(category)], "completeness_ratio": ratio, "status": "complete" if ratio >= threshold else "incomplete"}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
