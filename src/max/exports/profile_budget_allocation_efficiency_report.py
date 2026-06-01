"""Profile budget allocation efficiency export report."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

SCHEMA_VERSION = "max.profile_budget_allocation_efficiency_report.v1"
KIND = "max.profile_budget_allocation_efficiency_report"


def generate_profile_budget_allocation_efficiency_report(
    rows: Iterable[dict[str, Any]],
    *,
    min_efficiency: float = 0.0,
) -> dict[str, Any]:
    threshold = _float(min_efficiency)
    grouped: dict[str, dict[str, float]] = defaultdict(lambda: {"allocated_budget": 0.0, "useful_output": 0.0})
    for raw in rows:
        profile = _text(raw.get("profile") or raw.get("profile_id")) or "unknown-profile"
        grouped[profile]["allocated_budget"] += _float(raw.get("allocated_budget") or raw.get("allocation") or raw.get("budget"))
        grouped[profile]["useful_output"] += _float(raw.get("useful_output") or raw.get("realized_useful_output") or raw.get("output"))

    profile_rows = []
    for profile, totals in grouped.items():
        allocated = totals["allocated_budget"]
        useful = totals["useful_output"]
        efficiency = _rate(useful, allocated)
        profile_rows.append(
            {
                "profile": profile,
                "allocated_budget": round(allocated, 2),
                "useful_output": round(useful, 2),
                "efficiency": efficiency,
                "underperforming": efficiency < threshold,
            }
        )
    profile_rows.sort(key=lambda row: (row["efficiency"], row["profile"].casefold()))
    underperforming = [row for row in profile_rows if row["underperforming"]]
    total_allocated = sum(row["allocated_budget"] for row in profile_rows)
    total_useful = sum(row["useful_output"] for row in profile_rows)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "profile_count": len(profile_rows),
            "allocated_budget": round(total_allocated, 2),
            "useful_output": round(total_useful, 2),
            "efficiency": _rate(total_useful, total_allocated),
            "min_efficiency": threshold,
            "underperforming_count": len(underperforming),
        },
        "profiles": profile_rows,
        "underperforming_profiles": underperforming,
    }


def _rate(numerator: float, denominator: float) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _float(value: Any) -> float:
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return 0.0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
