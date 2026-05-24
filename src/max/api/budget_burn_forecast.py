"""JSON API renderer for budget burn forecasts."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any


SCHEMA_VERSION = "max.api.budget_burn_forecast.v1"
KIND = "max.api.budget_burn_forecast"


def budget_burn_forecast_to_json(payload: Mapping[str, Any]) -> str:
    """Render token and cost burn forecasts as deterministic API JSON."""
    stages = _remaining_stages(payload)
    summary = _summary(payload, stages)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "current_usage": _current_usage(payload),
        "limits": _limits(payload),
        "remaining_stages": stages,
        "summary": summary,
        "metadata": _metadata(payload, stages),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _summary(payload: Mapping[str, Any], stages: list[dict[str, Any]]) -> dict[str, Any]:
    usage = _current_usage(payload)
    limits = _limits(payload)
    estimated_tokens = sum(row["estimated_tokens"] for row in stages if row["estimated_tokens"] is not None)
    estimated_cost = sum(row["estimated_cost_usd"] for row in stages if row["estimated_cost_usd"] is not None)
    projected_tokens = usage["tokens_used"] + estimated_tokens
    projected_cost = round(usage["cost_usd"] + estimated_cost, 4)
    token_remaining = limits["token_limit"] - projected_tokens if limits["token_limit"] is not None else None
    cost_remaining = (
        round(limits["cost_limit_usd"] - projected_cost, 4)
        if limits["cost_limit_usd"] is not None
        else None
    )
    unknown_count = sum(1 for row in stages if row["estimate_status"] == "unknown")
    return {
        "projected_total_tokens": projected_tokens,
        "projected_total_cost_usd": projected_cost,
        "remaining_token_budget": token_remaining,
        "remaining_cost_budget_usd": cost_remaining,
        "unknown_stage_count": unknown_count,
        "overrun_risk": _risk(projected_tokens, projected_cost, limits, unknown_count),
    }


def _current_usage(payload: Mapping[str, Any]) -> dict[str, Any]:
    usage = _mapping(payload.get("current_usage"))
    return {
        "tokens_used": _int_or_zero(usage.get("tokens_used", payload.get("tokens_used"))),
        "cost_usd": _float_or_zero(usage.get("cost_usd", payload.get("cost_usd"))),
    }


def _limits(payload: Mapping[str, Any]) -> dict[str, Any]:
    limits = _mapping(payload.get("limits"))
    return {
        "token_limit": _optional_int(limits.get("token_limit", payload.get("token_limit"))),
        "cost_limit_usd": _optional_float(limits.get("cost_limit_usd", payload.get("cost_limit_usd"))),
    }


def _remaining_stages(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("remaining_stages")
    if not isinstance(source, list):
        source = payload.get("stage_estimates")
    rows = [
        _stage_row(item, index)
        for index, item in enumerate(source if isinstance(source, list) else [], start=1)
        if isinstance(item, Mapping)
    ]
    return sorted(rows, key=lambda row: (str(row["estimate_status"]), str(row["stage"])))


def _stage_row(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    tokens = _optional_int(item.get("estimated_tokens", item.get("tokens")))
    cost = _optional_float(item.get("estimated_cost_usd", item.get("cost_usd")))
    return {
        "stage": str(item.get("stage") or item.get("name") or f"stage-{index}"),
        "estimated_tokens": tokens,
        "estimated_cost_usd": cost,
        "estimate_status": "known" if tokens is not None or cost is not None else "unknown",
        "metadata": dict(_mapping(item.get("metadata"))),
    }


def _risk(
    projected_tokens: int,
    projected_cost: float,
    limits: Mapping[str, Any],
    unknown_count: int,
) -> str:
    token_limit = limits.get("token_limit")
    cost_limit = limits.get("cost_limit_usd")
    if (token_limit is not None and projected_tokens > token_limit) or (
        cost_limit is not None and projected_cost > cost_limit
    ):
        return "overrun"
    near_token = token_limit is not None and projected_tokens >= token_limit * 0.9
    near_cost = cost_limit is not None and projected_cost >= cost_limit * 0.9
    if near_token or near_cost or unknown_count:
        return "watch"
    return "within_budget"


def _metadata(payload: Mapping[str, Any], stages: list[dict[str, Any]]) -> dict[str, Any]:
    metadata = dict(_mapping(payload.get("metadata")))
    return {
        **metadata,
        "source_schema_version": metadata.get("source_schema_version") or payload.get("schema_version"),
        "source_kind": metadata.get("source_kind") or payload.get("kind"),
        "remaining_stage_count": len(stages),
    }


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        return None


def _int_or_zero(value: Any) -> int:
    return _optional_int(value) or 0


def _float_or_zero(value: Any) -> float:
    return _optional_float(value) or 0.0
