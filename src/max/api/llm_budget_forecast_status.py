"""JSON API renderer for LLM budget forecast status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import float_or_zero, int_or_zero, source_metadata

SCHEMA_VERSION = "max.api.llm_budget_forecast_status.v1"
KIND = "max.api.llm_budget_forecast_status"


def llm_budget_forecast_status_to_json(payload: Mapping[str, Any]) -> str:
    budget = round(max(0.0, float_or_zero(payload.get("budget_usd", payload.get("budget")))), 2)
    spend = round(max(0.0, float_or_zero(payload.get("current_spend_usd", payload.get("spend_usd")))), 2)
    burn = round(max(0.0, float_or_zero(payload.get("daily_burn_rate_usd", payload.get("daily_burn_rate")))), 2)
    reserved = round(max(0.0, float_or_zero(payload.get("reserved_budget_usd", payload.get("reserved_budget")))), 2)
    window = max(0, int_or_zero(payload.get("forecast_window_days", 7)))
    remaining = round(max(budget - spend - reserved, 0.0), 2)
    days = None if burn <= 0 else round(remaining / burn, 2)
    status = _status(budget, spend, remaining, days, window)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {"status": status, "budget_usd": budget, "current_spend_usd": spend, "reserved_budget_usd": reserved, "remaining_budget_usd": remaining, "daily_burn_rate_usd": burn},
        "forecast": {"forecast_window_days": window, "projected_exhaustion_days": days, "projected_exhaustion_date": payload.get("projected_exhaustion_date"), "severity": status},
        "metadata": source_metadata(payload),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _status(budget: float, spend: float, remaining: float, days: float | None, window: int) -> str:
    if budget <= 0:
        return "no_budget"
    if spend >= budget or remaining <= 0:
        return "exhausted"
    if days is not None and days <= window:
        return "warning"
    return "healthy"
