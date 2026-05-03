"""Aggregate LLM token and budget usage from runtime and persisted records."""

from __future__ import annotations

from math import isfinite
from typing import Mapping

from max import config
from max.llm.client import estimate_token_cost_usd, token_counts_from_usage


def _int_value(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _float_value(value: object) -> float | None:
    if not isinstance(value, (int, float)):
        return None
    return float(value)


def _remaining(limit: int | float, used: int | float) -> int | float | None:
    if limit <= 0:
        return None
    return limit - used


def _stage_usage_from_mapping(
    token_usage: Mapping[str, object],
    *,
    model: str,
) -> list[dict[str, object]]:
    """Normalize stage usage from persisted token tracker summaries."""
    stage_counts: dict[str, dict[str, int]] = {}

    by_stage = token_usage.get("by_stage")
    if isinstance(by_stage, Mapping):
        for stage, counts in by_stage.items():
            if not isinstance(counts, Mapping):
                continue
            name = str(stage)
            stage_counts[name] = {
                "input": _int_value(counts.get("input")),
                "output": _int_value(counts.get("output")),
            }

    for key, value in token_usage.items():
        if not isinstance(key, str):
            continue
        if key.endswith("_input"):
            stage = key[: -len("_input")]
            if stage == "total":
                continue
            stage_counts.setdefault(stage, {"input": 0, "output": 0})["input"] += _int_value(value)
        elif key.endswith("_output"):
            stage = key[: -len("_output")]
            if stage == "total":
                continue
            stage_counts.setdefault(stage, {"input": 0, "output": 0})["output"] += _int_value(value)

    cost_by_stage = token_usage.get("cost_by_stage")
    if not isinstance(cost_by_stage, Mapping):
        cost_by_stage = {}

    stages = []
    for stage, counts in sorted(stage_counts.items()):
        input_tokens = counts["input"]
        output_tokens = counts["output"]
        stored_cost = _float_value(cost_by_stage.get(stage))
        cost = (
            stored_cost
            if stored_cost is not None
            else estimate_token_cost_usd(input_tokens, output_tokens, model=model)
        )
        stages.append(
            {
                "stage": stage,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
                "estimated_cost_usd": cost,
            }
        )
    return stages


def _validate_stage_list(value: object) -> list[dict[str, object]]:
    """Validate and narrow a value to a list of stage dictionaries."""
    if not isinstance(value, list):
        return []
    result: list[dict[str, object]] = []
    for item in value:
        if isinstance(item, dict):
            result.append(item)
    return result


def _merge_stage_usage(target: dict[str, dict[str, float | int]], stages: list[dict[str, object]]) -> None:
    for stage in stages:
        name = str(stage["stage"])
        bucket = target.setdefault(
            name,
            {
                "stage": name,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "estimated_cost_usd": 0.0,
            },
        )
        bucket["input_tokens"] = int(bucket["input_tokens"]) + _int_value(stage.get("input_tokens"))
        bucket["output_tokens"] = int(bucket["output_tokens"]) + _int_value(stage.get("output_tokens"))
        bucket["total_tokens"] = int(bucket["total_tokens"]) + _int_value(stage.get("total_tokens"))
        bucket["estimated_cost_usd"] = float(bucket["estimated_cost_usd"]) + float(
            stage.get("estimated_cost_usd") or 0.0
        )


def _usage_from_tracker(tracker: object) -> dict[str, object]:
    usage = getattr(tracker, "usage", {}) or {}
    by_stage = getattr(tracker, "by_stage", {}) or {}
    model = str(getattr(tracker, "model", config.MODEL) or config.MODEL)
    input_tokens = _int_value(usage.get("input") if isinstance(usage, Mapping) else 0)
    output_tokens = _int_value(usage.get("output") if isinstance(usage, Mapping) else 0)
    stages = _stage_usage_from_mapping({"by_stage": by_stage}, model=model)
    cost = estimate_token_cost_usd(input_tokens, output_tokens, model=model)
    return {
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "estimated_cost_usd": cost,
        "stages": stages,
    }


def build_llm_budget_usage(
    store: object,
    *,
    limit: int = 20,
    include_current: bool = True,
    tracker: object | None = None,
) -> dict[str, object]:
    """Return JSON-ready LLM usage totals, budget limits, stages, and run history."""
    runs = store.get_pipeline_runs(limit=limit)
    total_input = 0
    total_output = 0
    total_cost = 0.0
    stage_totals: dict[str, dict[str, float | int]] = {}
    run_breakdown: list[dict[str, object]] = []

    for run in runs:
        token_usage = run.get("token_usage", {}) or {}
        model = str(run.get("config", {}).get("model") or config.MODEL)
        input_tokens, output_tokens = token_counts_from_usage(token_usage)
        stored_cost = _float_value(token_usage.get("estimated_cost_usd"))
        cost = (
            stored_cost
            if stored_cost is not None
            else estimate_token_cost_usd(input_tokens, output_tokens, model=model)
        )
        stages = _stage_usage_from_mapping(token_usage, model=model)

        total_input += input_tokens
        total_output += output_tokens
        total_cost += cost
        _merge_stage_usage(stage_totals, stages)
        run_breakdown.append(
            {
                "id": run["id"],
                "started_at": run["started_at"],
                "finished_at": run.get("completed_at"),
                "status": run.get("status") or ("completed" if run.get("completed_at") else "running"),
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
                "estimated_cost_usd": cost,
                "stages": stages,
                "token_usage": token_usage,
            }
        )

    current_usage = None
    if include_current:
        if tracker is None:
            from max.llm.client import token_tracker

            tracker = token_tracker
        current_usage = _usage_from_tracker(tracker)
        total_input += _int_value(current_usage["input_tokens"])
        total_output += _int_value(current_usage["output_tokens"])
        total_cost += float(current_usage["estimated_cost_usd"])
        _merge_stage_usage(stage_totals, _validate_stage_list(current_usage["stages"]))

    total_tokens = total_input + total_output
    token_limit = config.MAX_TOKEN_BUDGET
    cost_limit = config.MAX_COST_BUDGET
    remaining_cost = _remaining(cost_limit, total_cost)

    return {
        "limit": limit,
        "run_count": len(run_breakdown),
        "include_current": include_current,
        "model": config.MODEL,
        "total_input": total_input,
        "total_output": total_output,
        "total_tokens": total_tokens,
        "total_cost_usd": total_cost,
        "token_budget": token_limit,
        "cost_budget_usd": cost_limit,
        "remaining_tokens": _remaining(token_limit, total_tokens),
        "remaining_cost_usd": remaining_cost if remaining_cost is None or isfinite(remaining_cost) else None,
        "stages": sorted(stage_totals.values(), key=lambda item: str(item["stage"])),
        "current": current_usage,
        "runs": run_breakdown,
    }
