"""Portfolio coverage gap map across segments, stages, and categories."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Mapping


SCHEMA_VERSION = "max.portfolio_segment_gap_map.v1"
KIND = "max.portfolio_segment_gap_map"


def build_portfolio_segment_gap_map(
    items: list[Mapping[str, Any]],
    *,
    target_segments: list[str],
    lifecycle_stages: list[str],
    problem_categories: list[str],
    min_coverage: int = 1,
    max_coverage: int = 3,
) -> dict[str, Any]:
    """Compare portfolio coverage and identify underserved segment/category combinations."""

    counts = _coverage_counts(items)
    rows = [
        _coverage_row(segment, stage, category, counts, min_coverage, max_coverage)
        for segment in sorted({_clean(value) for value in target_segments if _clean(value)})
        for stage in sorted({_clean(value) for value in lifecycle_stages if _clean(value)})
        for category in sorted({_clean(value) for value in problem_categories if _clean(value)})
    ]
    rows.sort(key=lambda row: (_status_order(row["coverage_status"]), int(row["coverage_count"]), row["segment"], row["lifecycle_stage"], row["problem_category"]))

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "combination_count": len(rows),
            "gap_count": sum(1 for row in rows if row["coverage_status"] == "gap"),
            "balanced_count": sum(1 for row in rows if row["coverage_status"] == "balanced"),
            "saturation_risk_count": sum(1 for row in rows if row["coverage_status"] == "saturation_risk"),
        },
        "coverage_rows": rows,
    }


def render_portfolio_segment_gap_map_markdown(map_report: Mapping[str, Any]) -> str:
    """Render a portfolio segment gap map as deterministic Markdown."""

    summary = map_report["summary"]
    lines = [
        "# Portfolio Segment Gap Map",
        "",
        f"Schema: `{map_report['schema_version']}`",
        f"Combinations analyzed: {summary['combination_count']}",
        "",
        "## Coverage Summary",
        "",
        f"- Gaps: {summary['gap_count']}",
        f"- Balanced: {summary['balanced_count']}",
        f"- Saturation risk: {summary['saturation_risk_count']}",
        "",
        "## Most Underserved Combinations",
        "",
    ]

    rows = list(map_report.get("coverage_rows", []))
    gaps = [row for row in rows if row["coverage_status"] == "gap"]
    if gaps:
        for row in gaps[:10]:
            lines.extend(
                [
                    f"- {row['segment']} / {row['lifecycle_stage']} / {row['problem_category']}: "
                    f"{row['coverage_count']} item(s), focus: {row['suggested_ideation_focus']}",
                ]
            )
    else:
        lines.append("- No underserved combinations detected.")

    lines.extend(["", "## Coverage Detail", ""])
    if rows:
        for row in rows:
            lines.extend(
                [
                    f"### {row['segment']} / {row['lifecycle_stage']} / {row['problem_category']}",
                    "",
                    f"- Coverage count: {row['coverage_count']}",
                    f"- Status: {row['coverage_status']}",
                    f"- Suggested ideation focus: {row['suggested_ideation_focus']}",
                    "",
                ]
            )
    else:
        lines.append("No target combinations were configured.")

    return "\n".join(lines).rstrip() + "\n"


def _coverage_counts(items: list[Mapping[str, Any]]) -> dict[tuple[str, str, str], int]:
    counts: dict[tuple[str, str, str], int] = defaultdict(int)
    for item in items:
        for segment in _values(item.get("segment", item.get("target_segment"))):
            for stage in _values(item.get("lifecycle_stage", item.get("stage"))):
                for category in _values(item.get("problem_category", item.get("category"))):
                    key = (_clean(segment), _clean(stage), _clean(category))
                    if all(key):
                        counts[key] += 1
    return counts


def _coverage_row(
    segment: str,
    stage: str,
    category: str,
    counts: Mapping[tuple[str, str, str], int],
    min_coverage: int,
    max_coverage: int,
) -> dict[str, Any]:
    count = counts.get((segment, stage, category), 0)
    if count < min_coverage:
        status = "gap"
    elif count > max_coverage:
        status = "saturation_risk"
    else:
        status = "balanced"
    return {
        "segment": segment,
        "lifecycle_stage": stage,
        "problem_category": category,
        "coverage_count": count,
        "coverage_status": status,
        "suggested_ideation_focus": _focus(status, segment, stage, category, min_coverage, max_coverage, count),
    }


def _focus(status: str, segment: str, stage: str, category: str, min_coverage: int, max_coverage: int, count: int) -> str:
    if status == "gap":
        needed = min_coverage - count
        return f"create {needed} idea(s) for {segment} in {stage} around {category}"
    if status == "saturation_risk":
        return f"pause new ideation until coverage falls to {max_coverage} item(s) or less"
    return f"maintain coverage between {min_coverage} and {max_coverage} item(s)"


def _status_order(status: str) -> int:
    return {"gap": 0, "saturation_risk": 1, "balanced": 2}.get(status, 3)


def _values(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _clean(value: Any) -> str:
    return str(value or "").strip()
