"""Evaluation dataset coverage export report."""

from __future__ import annotations

import json
from typing import Any, Iterable

SCHEMA_VERSION = "max.evaluation_dataset_coverage_report.v1"
KIND = "max.evaluation_dataset_coverage_report"
DEFAULT_GENERATED_AT = "2026-05-27T00:00:00+00:00"


def build_evaluation_dataset_coverage_report(records: Iterable[dict[str, Any]], *, title: str = "Evaluation Dataset Coverage Report", generated_at: str = DEFAULT_GENERATED_AT, minimum_coverage_ratio: float = 0.8) -> dict[str, Any]:
    rows = []
    threshold = _clamp(minimum_coverage_ratio)
    for raw in records:
        expected = _int(raw.get("expected_cases"))
        actual = _int(raw.get("actual_cases"))
        ratio = _clamp(actual / expected) if expected else 0.0
        rows.append({"profile": _text(raw.get("profile")) or "unknown-profile", "source": _text(raw.get("source")) or "unknown-source", "dimension": _text(raw.get("dimension")) or "unknown-dimension", "expected_cases": expected, "actual_cases": actual, "coverage_ratio": ratio, "gap": ratio < threshold})
    rows.sort(key=lambda row: (row["profile"].lower(), row["source"].lower(), row["dimension"].lower()))
    under = [row for row in rows if row["gap"]]
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "generated_at": _text(generated_at) or DEFAULT_GENERATED_AT, "title": _text(title) or "Evaluation Dataset Coverage Report", "summary": {"profile_count": len({row["profile"] for row in rows}), "dimension_count": len({row["dimension"] for row in rows}), "average_coverage_ratio": round(sum(row["coverage_ratio"] for row in rows) / len(rows), 4) if rows else 0.0, "under_covered_dimension_count": len(under)}, "coverage": rows, "under_covered_dimensions": under}


def render_evaluation_dataset_coverage_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_evaluation_dataset_coverage_report_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    return "\n".join([f"# {report.get('title') or 'Evaluation Dataset Coverage Report'}", "", "## Summary", "", f"- Profiles: {summary.get('profile_count', 0)}", f"- Dimensions: {summary.get('dimension_count', 0)}", f"- Average coverage: {summary.get('average_coverage_ratio', 0.0)}", f"- Under-covered dimensions: {summary.get('under_covered_dimension_count', 0)}"]).rstrip() + "\n"


def _clamp(value: Any) -> float:
    try:
        return round(min(max(float(value), 0.0), 1.0), 4)
    except (TypeError, ValueError):
        return 0.0


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
