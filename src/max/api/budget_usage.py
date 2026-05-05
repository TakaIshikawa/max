"""JSON API endpoint renderer for budget usage reports."""

from __future__ import annotations

import json
from typing import Any

from max.analysis.budget_usage import build_llm_budget_usage


SCHEMA_VERSION = "max.api.budget_usage.v1"


def budget_usage_to_json(usage_data: dict[str, Any]) -> str:
    """
    Render a budget usage report as JSON for API endpoints.

    Args:
        usage_data: Budget usage dict from build_llm_budget_usage

    Returns:
        JSON string representation of the budget usage report
    """
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": "max.api.budget_usage",
        "summary": {
            "run_count": usage_data.get("run_count", 0),
            "model": usage_data.get("model", ""),
            "total_tokens": usage_data.get("total_tokens", 0),
            "total_input": usage_data.get("total_input", 0),
            "total_output": usage_data.get("total_output", 0),
            "total_cost_usd": usage_data.get("total_cost_usd", 0.0),
        },
        "budget_limits": {
            "token_budget": usage_data.get("token_budget", 0),
            "cost_budget_usd": usage_data.get("cost_budget_usd", 0.0),
            "remaining_tokens": usage_data.get("remaining_tokens"),
            "remaining_cost_usd": usage_data.get("remaining_cost_usd"),
        },
        "stage_aggregations": _format_stage_aggregations(usage_data.get("stages", [])),
        "current_session": _format_current_session(usage_data.get("current")) if usage_data.get("include_current") else None,
        "spend_by_category": _compute_spend_by_category(usage_data),
        "variance_metrics": _compute_variance_metrics(usage_data),
        "forecast_projections": _compute_forecast_projections(usage_data),
        "runs": _format_runs(usage_data.get("runs", [])),
    }

    return json.dumps(payload, indent=2, sort_keys=True)


def _format_stage_aggregations(stages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Format stage aggregation data for API response."""
    return [
        {
            "stage": stage.get("stage", ""),
            "input_tokens": stage.get("input_tokens", 0),
            "output_tokens": stage.get("output_tokens", 0),
            "total_tokens": stage.get("total_tokens", 0),
            "estimated_cost_usd": stage.get("estimated_cost_usd", 0.0),
        }
        for stage in stages
    ]


def _format_current_session(current: dict[str, Any] | None) -> dict[str, Any] | None:
    """Format current session data for API response."""
    if not current:
        return None

    return {
        "model": current.get("model", ""),
        "input_tokens": current.get("input_tokens", 0),
        "output_tokens": current.get("output_tokens", 0),
        "total_tokens": current.get("total_tokens", 0),
        "estimated_cost_usd": current.get("estimated_cost_usd", 0.0),
        "stages": _format_stage_aggregations(current.get("stages", [])),
    }


def _format_runs(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Format run breakdown data for API response."""
    return [
        {
            "id": run.get("id", ""),
            "started_at": run.get("started_at"),
            "finished_at": run.get("finished_at"),
            "status": run.get("status", ""),
            "model": run.get("model", ""),
            "total_tokens": run.get("total_tokens", 0),
            "estimated_cost_usd": run.get("estimated_cost_usd", 0.0),
        }
        for run in runs
    ]


def _compute_spend_by_category(usage_data: dict[str, Any]) -> dict[str, Any]:
    """Compute spend breakdown by category."""
    total_cost = usage_data.get("total_cost_usd", 0.0)
    stages = usage_data.get("stages", [])

    stage_costs = {
        stage.get("stage", "unknown"): stage.get("estimated_cost_usd", 0.0)
        for stage in stages
    }

    return {
        "by_stage": stage_costs,
        "total_cost_usd": total_cost,
        "stage_count": len(stage_costs),
    }


def _compute_variance_metrics(usage_data: dict[str, Any]) -> dict[str, Any]:
    """Compute variance and utilization metrics."""
    token_budget = usage_data.get("token_budget", 0)
    cost_budget = usage_data.get("cost_budget_usd", 0.0)
    total_tokens = usage_data.get("total_tokens", 0)
    total_cost = usage_data.get("total_cost_usd", 0.0)

    token_utilization = (total_tokens / token_budget * 100) if token_budget > 0 else 0.0
    cost_utilization = (total_cost / cost_budget * 100) if cost_budget > 0 else 0.0

    return {
        "token_utilization_percent": round(token_utilization, 2),
        "cost_utilization_percent": round(cost_utilization, 2),
        "over_token_budget": total_tokens > token_budget if token_budget > 0 else False,
        "over_cost_budget": total_cost > cost_budget if cost_budget > 0 else False,
    }


def _compute_forecast_projections(usage_data: dict[str, Any]) -> dict[str, Any]:
    """Compute forecast projections based on current usage patterns."""
    runs = usage_data.get("runs", [])
    run_count = len(runs)

    if run_count == 0:
        return {
            "projected_tokens_per_run": 0,
            "projected_cost_per_run_usd": 0.0,
            "runs_until_token_budget_exhausted": None,
            "runs_until_cost_budget_exhausted": None,
        }

    total_tokens = usage_data.get("total_tokens", 0)
    total_cost = usage_data.get("total_cost_usd", 0.0)
    remaining_tokens = usage_data.get("remaining_tokens")
    remaining_cost = usage_data.get("remaining_cost_usd")

    # Include current session in average calculation if present
    effective_runs = run_count
    if usage_data.get("include_current") and usage_data.get("current"):
        effective_runs += 1

    avg_tokens_per_run = total_tokens / effective_runs if effective_runs > 0 else 0
    avg_cost_per_run = total_cost / effective_runs if effective_runs > 0 else 0.0

    runs_until_token_exhausted = None
    if remaining_tokens is not None and avg_tokens_per_run > 0:
        runs_until_token_exhausted = int(remaining_tokens / avg_tokens_per_run)

    runs_until_cost_exhausted = None
    if remaining_cost is not None and avg_cost_per_run > 0:
        runs_until_cost_exhausted = int(remaining_cost / avg_cost_per_run)

    return {
        "projected_tokens_per_run": int(avg_tokens_per_run),
        "projected_cost_per_run_usd": round(avg_cost_per_run, 4),
        "runs_until_token_budget_exhausted": runs_until_token_exhausted,
        "runs_until_cost_budget_exhausted": runs_until_cost_exhausted,
    }
