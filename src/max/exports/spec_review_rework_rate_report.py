"""Spec review rework rate export report."""

from __future__ import annotations

import json
from typing import Any, Iterable, TypedDict

SCHEMA_VERSION = "max.spec_review_rework_rate_report.v1"
KIND = "max.spec_review_rework_rate_report"
DEFAULT_GENERATED_AT = "2026-05-20T00:00:00+00:00"


class SpecReviewReworkInput(TypedDict, total=False):
    spec_id: str
    title: str
    review_cycles: int | float | str
    rework_events: int | float | str
    last_reviewed_at: str
    owner: str


def build_spec_review_rework_rate_report(
    records: Iterable[SpecReviewReworkInput | dict[str, Any]],
    *,
    cycle_threshold: int = 2,
    title: str = "Spec Review Rework Rate Report",
    generated_at: str = DEFAULT_GENERATED_AT,
) -> dict[str, Any]:
    threshold = max(0, int(cycle_threshold))
    rows = [_row(raw, index, threshold) for index, raw in enumerate(records, start=1)]
    rows.sort(key=lambda row: (row["status"] == "healthy", -row["review_cycles"], -row["rework_events"], row["spec_id"].lower()))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": _text(generated_at) or DEFAULT_GENERATED_AT,
        "title": _text(title) or "Spec Review Rework Rate Report",
        "cycle_threshold": threshold,
        "summary": {
            "total_specs": len(rows),
            "specs_with_rework": sum(1 for row in rows if row["rework_events"] > 0),
            "average_review_cycles": round(sum(row["review_cycles"] for row in rows) / len(rows), 2) if rows else 0.0,
            "highest_review_cycles": max([row["review_cycles"] for row in rows] or [0]),
        },
        "spec_review_rows": rows,
        "rework_queue": [row for row in rows if row["status"] != "healthy"],
    }


def render_spec_review_rework_rate_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_spec_review_rework_rate_report_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    return "\n".join([
        f"# {report.get('title') or 'Spec Review Rework Rate Report'}",
        "",
        "## Summary",
        "",
        f"- Specs: {summary.get('total_specs', 0)}",
        f"- Specs with rework: {summary.get('specs_with_rework', 0)}",
    ]).rstrip() + "\n"


def _row(raw: dict[str, Any], index: int, threshold: int) -> dict[str, Any]:
    cycles = _int(raw.get("review_cycles") or raw.get("cycles"))
    rework = _int(raw.get("rework_events") or raw.get("rework_count"))
    return {
        "spec_id": _text(raw.get("spec_id") or raw.get("id")) or f"unknown-spec-{index}",
        "title": _text(raw.get("title")) or "Untitled spec",
        "review_cycles": cycles,
        "rework_events": rework,
        "last_reviewed_at": _text(raw.get("last_reviewed_at")),
        "owner": _text(raw.get("owner")) or "Unassigned",
        "status": "exceeds_threshold" if cycles > threshold else "healthy",
    }


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
