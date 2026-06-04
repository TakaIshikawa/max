"""JSON API renderer for buildable unit acceptance criteria completeness status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.buildable_unit_acceptance_criteria_completeness_status.v1"
KIND = "max.api.buildable_unit_acceptance_criteria_completeness_status"
STATUS_RANK = {"critical": 0, "warning": 1, "ok": 2}
OBSERVABLE_VERBS = ("assert", "verify", "test", "expect", "check", "measure", "return", "emit", "fail", "pass", "render", "classify")


def buildable_unit_acceptance_criteria_completeness_status_to_json(payload: Mapping[str, Any], *, minimum_criteria: int = 2, critical_missing_threshold: int = 0) -> str:
    minimum = max(1, int_or_zero(minimum_criteria))
    rows = [_row(item, index, minimum, critical_missing_threshold) for index, item in enumerate(_items(payload), start=1)]
    rows = sorted(rows, key=lambda row: (STATUS_RANK[row["status"]], row["criteria_count"], row["unit_id"]))
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"unit_count": len(rows), "incomplete_units": sum(1 for row in rows if row["status"] != "ok"), "critical_units": sum(1 for row in rows if row["status"] == "critical")}, "unit_rows": rows, "metadata": source_metadata(payload, unit_count=len(rows))}, indent=2, sort_keys=True)


def _items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list_of_maps(payload.get("units") or payload.get("rows") or payload.get("items"))


def _row(item: Mapping[str, Any], index: int, minimum: int, critical_missing: int) -> dict[str, Any]:
    criteria = _criteria(item.get("acceptance_criteria", item.get("criteria")))
    untestable = [criterion for criterion in criteria if not _observable(criterion)]
    missing = max(minimum - len(criteria), 0)
    status = "critical" if len(criteria) <= critical_missing or not criteria else "warning" if missing or untestable else "ok"
    return {"unit_id": _text(item.get("unit_id") or item.get("id")) or f"unit-{index}", "criteria_count": len(criteria), "missing_criteria_count": missing, "untestable_criteria_count": len(untestable), "acceptance_criteria": criteria, "test_command": _text(item.get("test_command")) or None, "recommendation": _text(item.get("recommendation")) or ("add observable acceptance criteria" if status != "ok" else "none"), "status": status}


def _criteria(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_text(item) for item in value if _text(item)]
    text = _text(value)
    return [text] if text else []


def _observable(value: str) -> bool:
    folded = value.casefold()
    return any(verb in folded for verb in OBSERVABLE_VERBS)


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
