"""Buildable unit scope creep export report."""

from __future__ import annotations

from typing import Any, Iterable

SCHEMA_VERSION = "max.buildable_unit_scope_creep_report.v1"
KIND = "max.buildable_unit_scope_creep_report"
SEVERITY_RANK = {"stack_changed": 0, "dependency_growth": 1, "acceptance_criteria_growth": 2, "stable": 3}


def generate_buildable_unit_scope_creep_report(
    records: Iterable[dict[str, Any]],
    *,
    added_criteria_warning: int = 2,
    added_dependency_warning: int = 2,
) -> dict[str, Any]:
    rows = [_row(raw, index, added_criteria_warning, added_dependency_warning) for index, raw in enumerate(records, start=1) if isinstance(raw, dict)]
    rows.sort(key=lambda row: (row["severity_rank"], -row["added_dependency_count"], -row["added_criteria_count"], row["unit_id"].casefold()))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "unit_count": len(rows),
            "creeping_unit_count": sum(1 for row in rows if row["reason"] != "stable"),
            "stack_change_count": sum(1 for row in rows if row["reason"] == "stack_changed"),
            "added_dependency_total": sum(row["added_dependency_count"] for row in rows),
        },
        "unit_rows": rows,
    }


def _row(raw: dict[str, Any], index: int, criteria_warning: int, dependency_warning: int) -> dict[str, Any]:
    original_criteria = _list(raw.get("original_acceptance_criteria"))
    current_criteria = _list(raw.get("current_acceptance_criteria"))
    added_dependencies = _list(raw.get("added_dependencies"))
    original_stack = _text(raw.get("original_stack"))
    current_stack = _text(raw.get("current_stack"))
    added_criteria_count = max(0, len(current_criteria) - len(original_criteria))
    added_dependency_count = len(added_dependencies)
    reason = _reason(original_stack, current_stack, added_dependency_count, added_criteria_count, dependency_warning, criteria_warning)
    return {
        "unit_id": _text(raw.get("unit_id") or raw.get("id")) or f"unit-{index}",
        "profile": _text(raw.get("profile")) or "default",
        "original_stack": original_stack or None,
        "current_stack": current_stack or None,
        "added_criteria_count": added_criteria_count,
        "added_dependency_count": added_dependency_count,
        "reason": reason,
        "severity_rank": SEVERITY_RANK[reason],
    }


def _reason(original_stack: str, current_stack: str, dependency_count: int, criteria_count: int, dependency_warning: int, criteria_warning: int) -> str:
    if original_stack and current_stack and original_stack.casefold() != current_stack.casefold():
        return "stack_changed"
    if dependency_count >= dependency_warning:
        return "dependency_growth"
    if criteria_count >= criteria_warning:
        return "acceptance_criteria_growth"
    return "stable"


def _list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [_text(item) for item in value if _text(item)]
    text = _text(value)
    if not text:
        return []
    return [part.strip() for part in text.split(",") if part.strip()]


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
