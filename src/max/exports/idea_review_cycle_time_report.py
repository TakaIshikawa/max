"""Idea review cycle time export report."""

from __future__ import annotations

import json
from datetime import datetime
from statistics import median
from typing import Any, Iterable, TypedDict

SCHEMA_VERSION = "max.idea_review_cycle_time_report.v1"
KIND = "max.idea_review_cycle_time_report"


class IdeaReviewCycleTimeInput(TypedDict, total=False):
    idea_id: str
    recommendation: str
    generated_at: str
    reviewed_at: str
    approved_at: str
    rejected_at: str
    spec_generated_at: str
    published_at: str


def build_idea_review_cycle_time_report(records: Iterable[IdeaReviewCycleTimeInput | dict[str, Any]], *, title: str = "Idea Review Cycle Time Report", delay_threshold_hours: int = 72) -> dict[str, Any]:
    rows = [_row(raw, index) for index, raw in enumerate(records)]
    delayed = [row for row in rows if row["total_cycle_hours"] is None or row["total_cycle_hours"] >= delay_threshold_hours]
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "title": _text(title) or "Idea Review Cycle Time Report", "summary": {"idea_count": len(rows), "delayed_idea_count": len(delayed)}, "ideas": sorted(rows, key=lambda row: (row["idea_id"].lower(), row["recommendation"].lower())), "stage_metrics": _stage_metrics(rows), "recommendation_metrics": _recommendation_metrics(rows), "delayed_ideas": sorted(delayed, key=lambda row: (-(row["total_cycle_hours"] or 10**9), row["idea_id"].lower())), "stage_bottlenecks": _bottlenecks(rows)}


def render_idea_review_cycle_time_report_markdown(report: dict[str, Any]) -> str:
    lines = [f"# {report.get('title') or 'Idea Review Cycle Time Report'}", "", "## Delayed Ideas", ""]
    delayed = report.get("delayed_ideas") or []
    if not delayed:
        lines.append("- No delayed ideas.")
    else:
        for row in delayed:
            value = "missing terminal timestamp" if row["total_cycle_hours"] is None else f"{row['total_cycle_hours']} hours"
            lines.append(f"- {row['idea_id']} ({row['recommendation']}): {value}")
    lines.extend(["", "## Stage Bottlenecks", ""])
    lines.extend([f"- {row['stage']}: median {row['median_hours']} hours, max {row['max_hours']} hours" for row in report.get("stage_bottlenecks") or []] or ["- No stage bottlenecks detected."])
    return "\n".join(lines).rstrip() + "\n"


def render_idea_review_cycle_time_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def _row(raw: dict[str, Any], index: int) -> dict[str, Any]:
    generated = _dt(raw.get("generated_at"))
    stages = {
        "review": _hours(generated, _dt(raw.get("reviewed_at"))),
        "approval": _hours(generated, _dt(raw.get("approved_at"))),
        "rejection": _hours(generated, _dt(raw.get("rejected_at"))),
        "spec_generation": _hours(generated, _dt(raw.get("spec_generated_at"))),
        "publication": _hours(generated, _dt(raw.get("published_at"))),
    }
    terminal = next((stages[key] for key in ("publication", "spec_generation", "approval", "rejection", "review") if stages[key] is not None), None)
    return {"idea_id": _text(raw.get("idea_id")) or f"idea-{index + 1}", "recommendation": _text(raw.get("recommendation") or raw.get("status")) or "unclassified", "generated_at": _text(raw.get("generated_at")), "stage_cycle_hours": stages, "total_cycle_hours": terminal}


def _stage_metrics(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_metric(stage, [row["stage_cycle_hours"][stage] for row in rows if row["stage_cycle_hours"][stage] is not None]) for stage in ("review", "approval", "rejection", "spec_generation", "publication")]


def _recommendation_metrics(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    values = sorted({row["recommendation"] for row in rows}, key=str.lower)
    return [{"recommendation": value, "idea_count": sum(1 for row in rows if row["recommendation"] == value), "median_total_hours": _median([row["total_cycle_hours"] for row in rows if row["recommendation"] == value and row["total_cycle_hours"] is not None]), "max_total_hours": max([row["total_cycle_hours"] for row in rows if row["recommendation"] == value and row["total_cycle_hours"] is not None] or [0])} for value in values]


def _bottlenecks(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted([row for row in _stage_metrics(rows) if row["max_hours"] > 0], key=lambda row: (-row["median_hours"], -row["max_hours"], row["stage"]))


def _metric(stage: str, values: list[float]) -> dict[str, Any]:
    return {"stage": stage, "count": len(values), "median_hours": _median(values), "max_hours": max(values or [0])}


def _median(values: list[float]) -> float:
    return round(float(median(values)), 2) if values else 0.0


def _hours(start: datetime | None, end: datetime | None) -> float | None:
    return round((end - start).total_seconds() / 3600, 2) if start and end and end >= start else None


def _dt(value: Any) -> datetime | None:
    text = _text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
