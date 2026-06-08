"""Spec acceptance criteria completeness export report."""

from __future__ import annotations

from typing import Any, Iterable

SCHEMA_VERSION = "max.spec_acceptance_criteria_completeness_report.v1"
KIND = "max.spec_acceptance_criteria_completeness_report"


def generate_spec_acceptance_criteria_completeness_report(
    records: Iterable[dict[str, Any]],
    *,
    specificity_min_words: int = 5,
) -> dict[str, Any]:
    min_words = max(1, _int(specificity_min_words))
    rows = []
    for index, raw in enumerate(records, start=1):
        if not isinstance(raw, dict):
            continue
        spec_id = _text(raw.get("spec_id") or raw.get("id") or raw.get("name")) or f"spec-{index}"
        criteria = [_text(item) for item in _criteria(raw) if _text(item)]
        seen: set[str] = set()
        duplicates = []
        vague = []
        for criterion in criteria:
            key = criterion.casefold()
            if key in seen:
                duplicates.append(criterion)
            seen.add(key)
            if len(criterion.split()) < min_words or not any(word in criterion.lower() for word in ("when", "then", "must", "should", "given", "verify", "test")):
                vague.append(criterion)
        issues = []
        if not criteria:
            issues.append("missing_criteria")
        if duplicates:
            issues.append("duplicate_criteria")
        if vague:
            issues.append("vague_or_untestable_criteria")
        rows.append({"spec_id": spec_id, "criteria_count": len(criteria), "missing_count": 1 if not criteria else 0, "duplicate_count": len(duplicates), "vague_count": len(vague), "issues": issues, "duplicate_criteria": duplicates, "vague_criteria": vague, "status": "incomplete" if issues else "complete"})
    rows.sort(key=lambda row: (row["status"] != "incomplete", row["spec_id"].casefold()))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"row_count": len(rows), "incomplete_count": sum(1 for row in rows if row["status"] == "incomplete"), "complete_count": sum(1 for row in rows if row["status"] == "complete"), "specificity_min_words": min_words}, "rows": rows}


def _criteria(raw: dict[str, Any]) -> list[Any]:
    value = raw.get("acceptance_criteria") or raw.get("criteria") or raw.get("acceptanceCriteria")
    if isinstance(value, list | tuple | set):
        return list(value)
    if isinstance(value, str):
        return [value]
    return []


def _int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
