"""Source allocation efficiency export report."""

from __future__ import annotations

import json
from typing import Any, Iterable, TypedDict

SCHEMA_VERSION = "max.source_allocation_efficiency.v1"
KIND = "max.source_allocation_efficiency"
DEFAULT_GENERATED_AT = "2026-05-20T00:00:00+00:00"


class SourceAllocationInput(TypedDict, total=False):
    source: str
    allocated_budget: int | float | str
    consumed_budget: int | float | str
    signal_count: int | float | str
    accepted_signal_count: int | float | str
    insight_count: int | float | str
    failure_count: int | float | str
    previous_weight: int | float | str
    current_weight: int | float | str


def build_source_allocation_efficiency_report(
    records: Iterable[SourceAllocationInput | dict[str, Any]],
    *,
    title: str = "Source Allocation Efficiency Report",
    generated_at: str = DEFAULT_GENERATED_AT,
) -> dict[str, Any]:
    rows = _normalize_records(records)
    underused = [row for row in rows if row["allocated_budget"] > 0 and row["budget_utilization"] < 0.5]
    overrun = [row for row in rows if row["allocated_budget"] > 0 and row["consumed_budget"] > row["allocated_budget"]]
    adjustments = [row for row in rows if row["weight_delta"] != 0.0]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": _text(generated_at) or DEFAULT_GENERATED_AT,
        "title": _text(title) or "Source Allocation Efficiency Report",
        "summary": {
            "source_count": len(rows),
            "allocated_budget": round(sum(row["allocated_budget"] for row in rows), 2),
            "consumed_budget": round(sum(row["consumed_budget"] for row in rows), 2),
            "signal_count": sum(row["signal_count"] for row in rows),
            "insight_count": sum(row["insight_count"] for row in rows),
            "underused_count": len(underused),
            "overrun_count": len(overrun),
        },
        "source_efficiency": rows,
        "underused_allocations": sorted(underused, key=lambda row: (row["budget_utilization"], row["source"].lower())),
        "overrun_allocations": sorted(overrun, key=lambda row: (-row["budget_overrun"], row["source"].lower())),
        "weight_adjustments": sorted(adjustments, key=lambda row: (-abs(row["weight_delta"]), row["source"].lower())),
    }


def render_source_allocation_efficiency_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        f"# {report.get('title') or 'Source Allocation Efficiency Report'}",
        "",
        "## Summary",
        "",
        f"- Sources: {summary.get('source_count', 0)}",
        f"- Underused allocations: {summary.get('underused_count', 0)}",
        f"- Overrun allocations: {summary.get('overrun_count', 0)}",
    ]
    return "\n".join(lines).rstrip() + "\n"


def render_source_allocation_efficiency_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def _normalize_records(records: Iterable[SourceAllocationInput | dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for raw in records:
        allocated = _float(raw.get("allocated_budget"))
        consumed = _float(raw.get("consumed_budget"))
        signals = _int(raw.get("signal_count"))
        accepted = _int(raw.get("accepted_signal_count"))
        insights = _int(raw.get("insight_count"))
        previous = _float(raw.get("previous_weight"))
        current = _float(raw.get("current_weight"))
        rows.append(
            {
                "source": _text(raw.get("source")) or "Unknown source",
                "allocated_budget": round(allocated, 2),
                "consumed_budget": round(consumed, 2),
                "budget_utilization": _rate(consumed, allocated),
                "budget_overrun": round(max(0.0, consumed - allocated), 2),
                "signal_count": signals,
                "accepted_signal_count": accepted,
                "insight_count": insights,
                "failure_count": _int(raw.get("failure_count")),
                "yield_per_budget": _rate(signals, consumed),
                "acceptance_rate": _rate(accepted, signals),
                "insight_yield": _rate(insights, accepted),
                "previous_weight": round(previous, 4),
                "current_weight": round(current, 4),
                "weight_delta": round(current - previous, 4),
            }
        )
    rows.sort(key=lambda row: (-row["yield_per_budget"], row["source"].lower()))
    return rows


def _rate(numerator: float, denominator: float) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _float(value: Any) -> float:
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return 0.0


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
