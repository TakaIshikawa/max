"""LLM token efficiency report for recent pipeline runs."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from max.analysis.pipeline_run_export import _budget_summary, _domain_name, _profile_name, _run_status

if TYPE_CHECKING:
    from max.store.db import Store


SCHEMA_VERSION = "max.llm_token_efficiency.v1"
KIND = "max.llm_token_efficiency"

_BAND_ORDER = {"high_token_low_output": 0, "watch": 1, "efficient": 2, "missing_usage": 3}


def build_llm_token_efficiency_report(store: "Store", *, limit: int = 50) -> dict[str, Any]:
    """Summarize token usage, cost, and output yield for recent pipeline runs."""
    if limit < 1:
        raise ValueError("limit must be at least 1")

    runs = [_run_row(store, run) for run in store.get_pipeline_runs(limit=limit)]
    runs.sort(key=_run_sort_key)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "filters": {"limit": limit},
        "summary": _summary(runs),
        "runs": runs,
        "rollups": {
            "models": _rollups(runs, "model"),
            "providers": _rollups(runs, "provider"),
        },
        "efficiency_bands": {
            band: [run["id"] for run in runs if run["efficiency_band"] == band]
            for band in _BAND_ORDER
        },
        "next_actions": _next_actions(runs),
    }


def _run_row(store: "Store", run: Mapping[str, Any]) -> dict[str, Any]:
    run_id = str(run.get("id") or "")
    domains = store.get_pipeline_run_domains(run_id)
    outputs = store.get_pipeline_run_output_counts(run_id)
    budget = _budget_summary(run)
    token_usage = budget.get("token_usage") if isinstance(budget.get("token_usage"), Mapping) else {}
    config = run.get("config") if isinstance(run.get("config"), Mapping) else {}
    input_tokens = _int(budget.get("input_tokens")) or _int(token_usage.get("input_tokens"))
    output_tokens = _int(budget.get("output_tokens")) or _int(token_usage.get("output_tokens"))
    total_tokens = input_tokens + output_tokens
    signal_count = _int(run.get("signals_fetched"))
    unit_count = _int(run.get("ideas_generated"))
    output_count = signal_count + _int(run.get("insights_generated")) + unit_count + _int(outputs.get("approved")) + _int(outputs.get("published"))
    row = {
        "id": run_id,
        "started_at": run.get("started_at"),
        "status": _run_status(run),
        "profile": _profile_name(run) or "unknown",
        "domain": _domain_name(run, domains) or "mixed/unknown",
        "provider": str(token_usage.get("provider") or config.get("provider") or "unknown"),
        "model": str(token_usage.get("model") or budget.get("model") or config.get("model") or "unknown"),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "estimated_cost_usd": round(float(budget.get("estimated_cost_usd") or 0.0), 6),
        "signals_fetched": signal_count,
        "unit_count": unit_count,
        "output_count": output_count,
        "token_per_signal": _ratio(total_tokens, signal_count),
        "token_per_unit": _ratio(total_tokens, unit_count),
        "tokens_per_output": _ratio(total_tokens, output_count),
        "missing_usage": total_tokens == 0,
    }
    row["efficiency_band"] = _efficiency_band(row)
    return row


def _efficiency_band(row: Mapping[str, Any]) -> str:
    if row.get("missing_usage"):
        return "missing_usage"
    total_tokens = int(row.get("total_tokens") or 0)
    output_count = int(row.get("output_count") or 0)
    if total_tokens >= 10000 and output_count <= 2:
        return "high_token_low_output"
    if total_tokens >= 3000 and (output_count <= 2 or float(row.get("tokens_per_output") or 0.0) >= 1000):
        return "watch"
    return "efficient"


def _summary(runs: list[dict[str, Any]]) -> dict[str, Any]:
    total_tokens = sum(int(run["total_tokens"]) for run in runs)
    output_count = sum(int(run["output_count"]) for run in runs)
    total_cost = round(sum(float(run["estimated_cost_usd"]) for run in runs), 6)
    return {
        "run_count": len(runs),
        "total_input_tokens": sum(int(run["input_tokens"]) for run in runs),
        "total_output_tokens": sum(int(run["output_tokens"]) for run in runs),
        "total_tokens": total_tokens,
        "total_estimated_cost_usd": total_cost,
        "output_count": output_count,
        "tokens_per_output": _ratio(total_tokens, output_count),
        "high_token_low_output_count": sum(1 for run in runs if run["efficiency_band"] == "high_token_low_output"),
        "missing_usage_count": sum(1 for run in runs if run["efficiency_band"] == "missing_usage"),
    }


def _rollups(runs: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for run in runs:
        name = str(run.get(key) or "unknown")
        row = grouped.setdefault(
            name,
            {
                key: name,
                "run_count": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "estimated_cost_usd": 0.0,
                "output_count": 0,
                "high_token_low_output_count": 0,
                "missing_usage_count": 0,
            },
        )
        row["run_count"] += 1
        row["input_tokens"] += int(run["input_tokens"])
        row["output_tokens"] += int(run["output_tokens"])
        row["total_tokens"] += int(run["total_tokens"])
        row["estimated_cost_usd"] += float(run["estimated_cost_usd"])
        row["output_count"] += int(run["output_count"])
        row["high_token_low_output_count"] += int(run["efficiency_band"] == "high_token_low_output")
        row["missing_usage_count"] += int(run["efficiency_band"] == "missing_usage")
    rows = []
    for row in grouped.values():
        row["estimated_cost_usd"] = round(float(row["estimated_cost_usd"]), 6)
        row["tokens_per_output"] = _ratio(row["total_tokens"], row["output_count"])
        rows.append(row)
    return sorted(rows, key=lambda row: (-int(row["high_token_low_output_count"]), -int(row["total_tokens"]), str(row.get(key) or "")))


def _next_actions(runs: list[dict[str, Any]]) -> list[str]:
    if not runs:
        return ["Run the pipeline before reviewing LLM token efficiency."]
    missing = [run for run in runs if run["efficiency_band"] == "missing_usage"]
    costly = [run for run in runs if run["efficiency_band"] == "high_token_low_output"]
    actions: list[str] = []
    if costly:
        actions.append("Review prompt volume and generation thresholds for high-token low-output runs: " + ", ".join(run["id"] for run in costly[:3]) + ".")
    if missing:
        actions.append("Enable token usage tracking for runs missing usage data: " + ", ".join(run["id"] for run in missing[:3]) + ".")
    if not actions:
        actions.append("Keep current token budgets and compare model rollups after the next run batch.")
    return actions


def _run_sort_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        _BAND_ORDER.get(str(row.get("efficiency_band") or ""), 99),
        -int(row.get("total_tokens") or 0),
        int(row.get("output_count") or 0),
        str(row.get("started_at") or ""),
        str(row.get("id") or ""),
    )


def _ratio(numerator: int | float, denominator: int | float) -> float | None:
    if not denominator:
        return None
    return round(float(numerator) / float(denominator), 6)


def _int(value: object) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0
