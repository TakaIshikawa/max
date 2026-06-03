"""JSON API renderer for spec template variable coverage status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import float_or_zero, int_or_zero, list_of_maps, source_metadata, strings

SCHEMA_VERSION = "max.api.spec_template_variable_coverage_status.v1"
KIND = "max.api.spec_template_variable_coverage_status"
STATUS_RANK = {"critical": 0, "warning": 1, "ok": 2}
BLOCKER_VARIABLES = {"profile", "unit_id", "acceptance_criteria", "title"}


def spec_template_variable_coverage_status_to_json(payload: Mapping[str, Any]) -> str:
    warning = _float(payload.get("warning_coverage_ratio"), 0.95)
    critical = _float(payload.get("critical_coverage_ratio"), 0.8)
    blockers = set(strings(payload.get("blocker_variables"))) or BLOCKER_VARIABLES
    rows = sorted([_row(item, index, warning, critical, blockers) for index, item in enumerate(_items(payload), start=1)], key=lambda row: (STATUS_RANK[row["status"]], row["coverage_ratio"], row["template"]))
    summary = _summary(rows)
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "status": summary["status"], "summary": summary, "templates": rows, "metadata": source_metadata(payload, template_count=len(rows))}, indent=2, sort_keys=True)


def _items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list_of_maps(payload.get("templates") or payload.get("items") or payload.get("rows"))


def _row(item: Mapping[str, Any], index: int, warning: float, critical: float, blockers: set[str]) -> dict[str, Any]:
    required = max(0, int_or_zero(item.get("required_variable_count")))
    populated = max(0, int_or_zero(item.get("populated_variable_count")))
    missing = strings(item.get("missing_variables"))
    missing_count = max(len(missing), max(required - populated, 0))
    ratio = round(populated / required, 4) if required else 1.0
    blocker_missing = any(name in blockers for name in missing)
    status = "critical" if ratio < critical or blocker_missing else "warning" if ratio < warning else "ok"
    return {"template": _text(item.get("template")) or f"template-{index}", "required_variable_count": required, "populated_variable_count": populated, "optional_variable_count": max(0, int_or_zero(item.get("optional_variable_count"))), "coverage_ratio": ratio, "missing_variables": missing, "missing_required_count": missing_count, "blocker_missing": blocker_missing, "status": status}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    critical = sum(1 for row in rows if row["status"] == "critical")
    warning = sum(1 for row in rows if row["status"] == "warning")
    return {"status": "critical" if critical else "warning" if warning else "ok", "template_count": len(rows), "incomplete_template_count": critical + warning, "critical_count": critical, "warning_count": warning, "lowest_coverage_ratio": min((row["coverage_ratio"] for row in rows), default=1.0)}


def _float(value: Any, default: float) -> float:
    parsed = float_or_zero(value if value is not None else default)
    return parsed if parsed > 0 else default


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
