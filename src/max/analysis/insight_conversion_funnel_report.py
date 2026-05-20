"""Insight-to-idea conversion funnel report."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store
    from max.types.buildable_unit import BuildableUnit
    from max.types.insight import Insight


SCHEMA_VERSION = "max.insight_conversion_funnel.v1"
KIND = "max.insight_conversion_funnel"

_BAND_ORDER = {"no_units": 0, "weak_approval": 1, "healthy": 2, "no_insights": 3}


def build_insight_conversion_funnel_report(store: "Store", *, limit: int = 100) -> dict[str, Any]:
    """Build a deterministic conversion report from insights to approved or published specs."""
    if limit < 1:
        raise ValueError("limit must be at least 1")

    insights = store.get_insights(limit=limit)
    units = store.get_buildable_units(limit=limit)
    rows = _funnel_rows(insights, units)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "filters": {"limit": limit},
        "summary": _summary(insights, units, rows),
        "funnel_rows": rows,
        "dropoff_bands": {
            band: [row["cohort_key"] for row in rows if row["dropoff_band"] == band]
            for band in _BAND_ORDER
        },
        "next_actions": _next_actions(rows),
    }


def _funnel_rows(insights: list["Insight"], units: list["BuildableUnit"]) -> list[dict[str, Any]]:
    insight_by_id = {insight.id: insight for insight in insights}
    grouped: dict[tuple[str, str], dict[str, Any]] = {}

    for insight in insights:
        _ensure_group(grouped, "category", str(insight.category)).setdefault("_insight_ids", set()).add(insight.id)
        for domain in sorted(set(insight.domains or ["unknown"])):
            _ensure_group(grouped, "domain", domain or "unknown").setdefault("_insight_ids", set()).add(insight.id)

    for unit in units:
        linked = [insight_by_id[item] for item in unit.inspiring_insights if item in insight_by_id]
        profiles = sorted({_unit_profile(unit)})
        domains = sorted({domain for insight in linked for domain in insight.domains} or {unit.domain or "unknown"})
        categories = sorted({str(insight.category) for insight in linked} or {"unknown"})
        cohorts = {("profile", profile) for profile in profiles}
        cohorts.update(("domain", domain or "unknown") for domain in domains)
        cohorts.update(("category", category) for category in categories)

        for cohort_type, cohort in sorted(cohorts):
            row = _ensure_group(grouped, cohort_type, cohort)
            row.setdefault("_unit_ids", set()).add(unit.id)
            if unit.status == "approved":
                row.setdefault("_approved_ids", set()).add(unit.id)
            if unit.status == "published":
                row.setdefault("_published_ids", set()).add(unit.id)

    rows = [_finalize_row(row) for row in grouped.values()]
    return sorted(rows, key=_row_sort_key)


def _ensure_group(grouped: dict[tuple[str, str], dict[str, Any]], cohort_type: str, cohort: str) -> dict[str, Any]:
    return grouped.setdefault(
        (cohort_type, cohort),
        {
            "cohort_type": cohort_type,
            "cohort": cohort,
            "cohort_key": f"{cohort_type}:{cohort}",
            "_insight_ids": set(),
            "_unit_ids": set(),
            "_approved_ids": set(),
            "_published_ids": set(),
        },
    )


def _finalize_row(row: dict[str, Any]) -> dict[str, Any]:
    insight_count = len(row.get("_insight_ids", set()))
    unit_count = len(row.get("_unit_ids", set()))
    approved_count = len(row.get("_approved_ids", set()))
    published_count = len(row.get("_published_ids", set()))
    accepted_count = approved_count + published_count
    finalized = {
        "cohort_type": row["cohort_type"],
        "cohort": row["cohort"],
        "cohort_key": row["cohort_key"],
        "insight_count": insight_count,
        "unit_count": unit_count,
        "approved_count": approved_count,
        "published_count": published_count,
        "accepted_count": accepted_count,
        "insight_to_unit_conversion_rate": _rate(unit_count, insight_count),
        "unit_to_accepted_conversion_rate": _rate(accepted_count, unit_count),
        "insight_to_accepted_conversion_rate": _rate(accepted_count, insight_count),
        "unit_dropoff_rate": _dropoff(unit_count, insight_count),
        "acceptance_dropoff_rate": _dropoff(accepted_count, unit_count),
    }
    finalized["dropoff_band"] = _dropoff_band(finalized)
    finalized["dropoff_stage"] = _dropoff_stage(finalized)
    return finalized


def _dropoff_band(row: Mapping[str, Any]) -> str:
    if int(row.get("insight_count") or 0) == 0:
        return "no_insights"
    if int(row.get("unit_count") or 0) == 0:
        return "no_units"
    if float(row.get("unit_to_accepted_conversion_rate") or 0.0) < 0.5:
        return "weak_approval"
    return "healthy"


def _dropoff_stage(row: Mapping[str, Any]) -> str:
    if row.get("dropoff_band") == "no_units":
        return "insight_to_unit"
    if row.get("dropoff_band") == "weak_approval":
        return "unit_to_accepted"
    if row.get("dropoff_band") == "no_insights":
        return "missing_insight_lineage"
    return "none"


def _summary(
    insights: list["Insight"],
    units: list["BuildableUnit"],
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    accepted = sum(1 for unit in units if unit.status in {"approved", "published"})
    return {
        "insight_count": len(insights),
        "unit_count": len(units),
        "accepted_count": accepted,
        "overall_insight_to_unit_conversion_rate": _rate(len(units), len(insights)),
        "overall_unit_to_accepted_conversion_rate": _rate(accepted, len(units)),
        "funnel_row_count": len(rows),
        "weak_funnel_count": sum(1 for row in rows if row["dropoff_band"] in {"no_units", "weak_approval"}),
    }


def _next_actions(rows: list[dict[str, Any]]) -> list[str]:
    weak = [row for row in rows if row["dropoff_band"] in {"no_units", "weak_approval", "no_insights"}]
    if not rows:
        return ["Create insights and linked buildable units before reviewing conversion funnels."]
    if weak:
        names = ", ".join(f"{row['cohort_key']}:{row['dropoff_stage']}" for row in weak[:3])
        return [f"Inspect weak conversion stages and add follow-up synthesis or approval review for {names}."]
    return ["Maintain current insight synthesis thresholds and monitor the next conversion batch."]


def _row_sort_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
    band = str(row.get("dropoff_band") or "")
    return (
        _BAND_ORDER.get(band, 99),
        float(row.get("insight_to_accepted_conversion_rate") or 0.0),
        float(row.get("unit_to_accepted_conversion_rate") or 0.0),
        -int(row.get("insight_count") or 0),
        str(row.get("cohort_type") or ""),
        str(row.get("cohort") or ""),
    )


def _unit_profile(unit: "BuildableUnit") -> str:
    value = unit.suggested_stack.get("profile") if isinstance(unit.suggested_stack, dict) else None
    return str(value or unit.domain or "unknown")


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return round(numerator / denominator, 6)


def _dropoff(converted: int, total: int) -> float | None:
    rate = _rate(converted, total)
    return None if rate is None else round(1.0 - rate, 6)
