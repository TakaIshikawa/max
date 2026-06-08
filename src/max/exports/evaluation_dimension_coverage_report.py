"""Evaluation dimension coverage export report."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

SCHEMA_VERSION = "max.evaluation_dimension_coverage_report.v1"
KIND = "max.evaluation_dimension_coverage_report"
DEFAULT_DIMENSIONS = ("accuracy", "relevance", "novelty", "evidence", "feasibility", "risk", "clarity")
_STATUS_ORDER = {"sparse": 0, "partial": 1, "complete": 2}


def generate_evaluation_dimension_coverage_report(evaluations: Iterable[dict[str, Any]], *, expected_dimensions: Iterable[str] = DEFAULT_DIMENSIONS, partial_threshold: float = 0.7) -> dict[str, Any]:
    expected = tuple(_text(item) for item in expected_dimensions if _text(item)) or DEFAULT_DIMENSIONS
    groups: dict[tuple[str, str], dict[str, Any]] = defaultdict(lambda: {"evals": 0, "dims": set(), "partial": 0})
    for raw in evaluations:
        if not isinstance(raw, dict):
            continue
        key = (_text(raw.get("profile") or raw.get("profile_id")) or "default", _text(raw.get("rubric_version") or raw.get("version")) or "unknown")
        dims = {_text(item) for item in (raw.get("dimensions") or raw.get("dimension_names") or []) if _text(item)}
        scores = raw.get("scores")
        if isinstance(scores, dict):
            dims.update(_text(key) for key in scores if _text(key))
        groups[key]["evals"] += 1
        groups[key]["dims"].update(dims)
        if len(dims.intersection(expected)) < len(expected):
            groups[key]["partial"] += 1
    rows = []
    for (profile, rubric_version), group in groups.items():
        missing = [dim for dim in expected if dim not in group["dims"]]
        coverage = round((len(expected) - len(missing)) / len(expected), 4) if expected else 1.0
        rows.append({"profile": profile, "rubric_version": rubric_version, "evaluation_count": group["evals"], "coverage_percent": round(coverage * 100, 2), "missing_dimensions": missing, "partial_evaluation_count": group["partial"], "status": "complete" if not missing else ("partial" if coverage >= partial_threshold else "sparse")})
    rows.sort(key=lambda row: (_STATUS_ORDER[row["status"]], row["profile"].casefold(), row["rubric_version"].casefold()))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"status": rows[0]["status"] if rows else "complete", "group_count": len(rows), "expected_dimensions": list(expected), "partial_evaluation_count": sum(row["partial_evaluation_count"] for row in rows)}, "rows": rows}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().lower().split()) if value is not None else ""
