"""Profile and domain budget efficiency report for recent pipeline runs."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from max.analysis.pipeline_run_export import _budget_summary, _domain_name, _profile_name

if TYPE_CHECKING:
    from max.store.db import Store


SCHEMA_VERSION = "max.profile_budget_efficiency.v1"
KIND = "max.profile_budget_efficiency"

_BAND_ORDER = {"high_cost_low_yield": 0, "watch": 1, "efficient": 2, "zero_cost": 3, "zero_output": 4}


def build_profile_budget_efficiency_report(store: "Store", *, limit: int = 50) -> dict[str, Any]:
    """Compare pipeline spend against generated output by profile and domain."""
    if limit < 1:
        raise ValueError("limit must be at least 1")

    runs = [_run_metrics(store, run) for run in store.get_pipeline_runs(limit=limit)]
    rows = _cohort_rows(runs)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "filters": {"limit": limit},
        "summary": _summary(runs, rows),
        "rows": rows,
        "efficiency_bands": {
            band: [row["cohort_key"] for row in rows if row["efficiency_band"] == band]
            for band in _BAND_ORDER
        },
        "next_actions": _next_actions(rows),
    }


def _run_metrics(store: "Store", run: Mapping[str, Any]) -> dict[str, Any]:
    run_id = str(run.get("id") or "")
    domains = store.get_pipeline_run_domains(run_id)
    outputs = store.get_pipeline_run_output_counts(run_id)
    budget = _budget_summary(run)
    profile = _profile_name(run) or "unknown"
    domain = _domain_name(run, domains) or "mixed/unknown"
    return {
        "run_id": run_id,
        "profile": profile,
        "domain": domain,
        "estimated_cost_usd": round(float(budget.get("estimated_cost_usd") or 0.0), 6),
        "signals_fetched": _int(run.get("signals_fetched")),
        "signals_new": _int(run.get("signals_new")),
        "insights_generated": _int(run.get("insights_generated")),
        "ideas_generated": _int(run.get("ideas_generated")),
        "ideas_evaluated": _int(run.get("ideas_evaluated")),
        "approved_count": _int(outputs.get("approved")),
        "published_count": _int(outputs.get("published")),
        "domain_stats": domains,
    }


def _cohort_rows(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for run in runs:
        _add_to_group(grouped, "profile", run["profile"], run)
        if run["domain_stats"]:
            share = run["estimated_cost_usd"] / len(run["domain_stats"])
            for domain in run["domain_stats"]:
                _add_to_group(
                    grouped,
                    "domain",
                    str(domain.get("domain") or "unknown"),
                    {
                        **run,
                        "estimated_cost_usd": share,
                        "signals_fetched": _int(domain.get("signals_fetched")),
                        "insights_generated": _int(domain.get("insights_generated")),
                        "ideas_generated": _int(domain.get("ideas_generated")),
                        "ideas_evaluated": _int(domain.get("ideas_evaluated")),
                    },
                )
        else:
            _add_to_group(grouped, "domain", run["domain"], run)

    rows = [_finalize_row(item) for item in grouped.values()]
    return sorted(rows, key=_row_sort_key)


def _add_to_group(
    grouped: dict[tuple[str, str], dict[str, Any]],
    cohort_type: str,
    cohort: str,
    run: Mapping[str, Any],
) -> None:
    item = grouped.setdefault(
        (cohort_type, cohort),
        {
            "cohort_type": cohort_type,
            "cohort": cohort,
            "cohort_key": f"{cohort_type}:{cohort}",
            "run_count": 0,
            "estimated_cost_usd": 0.0,
            "signals_fetched": 0,
            "signals_new": 0,
            "insights_generated": 0,
            "ideas_generated": 0,
            "ideas_evaluated": 0,
            "approved_count": 0,
            "published_count": 0,
        },
    )
    item["run_count"] += 1
    item["estimated_cost_usd"] += float(run.get("estimated_cost_usd") or 0.0)
    for key in (
        "signals_fetched",
        "signals_new",
        "insights_generated",
        "ideas_generated",
        "ideas_evaluated",
        "approved_count",
        "published_count",
    ):
        item[key] += _int(run.get(key))


def _finalize_row(item: dict[str, Any]) -> dict[str, Any]:
    cost = round(float(item["estimated_cost_usd"]), 6)
    signals = int(item["signals_fetched"])
    ideas = int(item["ideas_generated"])
    output_count = signals + int(item["insights_generated"]) + ideas + int(item["approved_count"]) + int(item["published_count"])
    row = {
        **item,
        "estimated_cost_usd": cost,
        "output_count": output_count,
        "cost_per_signal": _ratio(cost, signals),
        "cost_per_idea": _ratio(cost, ideas),
        "output_yield": _ratio(output_count, cost),
    }
    row["efficiency_band"] = _efficiency_band(row)
    return row


def _efficiency_band(row: Mapping[str, Any]) -> str:
    cost = float(row.get("estimated_cost_usd") or 0.0)
    outputs = int(row.get("output_count") or 0)
    cost_per_idea = row.get("cost_per_idea")
    if cost == 0:
        return "zero_cost"
    if outputs == 0:
        return "zero_output"
    if cost >= 1.0 and (int(row.get("ideas_generated") or 0) == 0 or float(cost_per_idea or 0.0) >= 0.5):
        return "high_cost_low_yield"
    if cost >= 0.25 and (int(row.get("ideas_generated") or 0) == 0 or float(cost_per_idea or 0.0) >= 0.25):
        return "watch"
    return "efficient"


def _summary(runs: list[dict[str, Any]], rows: list[dict[str, Any]]) -> dict[str, Any]:
    total_cost = round(sum(float(run["estimated_cost_usd"]) for run in runs), 6)
    return {
        "run_count": len(runs),
        "row_count": len(rows),
        "total_estimated_cost_usd": total_cost,
        "total_signals_fetched": sum(int(run["signals_fetched"]) for run in runs),
        "total_ideas_generated": sum(int(run["ideas_generated"]) for run in runs),
        "high_cost_low_yield_count": sum(1 for row in rows if row["efficiency_band"] == "high_cost_low_yield"),
        "zero_output_count": sum(1 for row in rows if row["output_count"] == 0),
    }


def _next_actions(rows: list[dict[str, Any]]) -> list[str]:
    risky = [row for row in rows if row["efficiency_band"] in {"high_cost_low_yield", "zero_output"}]
    if not rows:
        return ["Run the pipeline before reviewing profile budget efficiency."]
    if risky:
        names = ", ".join(row["cohort_key"] for row in risky[:3])
        return [f"Review source allocation and generation thresholds for high-cost low-yield cohorts: {names}."]
    return ["Keep current profile budgets and compare efficiency after the next run batch."]


def _row_sort_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
    band = str(row.get("efficiency_band") or "")
    return (
        _BAND_ORDER.get(band, 99),
        -float(row.get("estimated_cost_usd") or 0.0),
        -float(row.get("cost_per_idea") or 0.0),
        str(row.get("cohort_type") or ""),
        str(row.get("cohort") or ""),
    )


def _ratio(numerator: float | int, denominator: float | int) -> float | None:
    if not denominator:
        return None
    return round(float(numerator) / float(denominator), 6)


def _int(value: object) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0
