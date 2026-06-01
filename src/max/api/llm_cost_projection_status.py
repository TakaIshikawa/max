"""JSON API renderer for LLM cost projection status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import float_or_zero, int_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.llm_cost_projection_status.v1"
KIND = "max.api.llm_cost_projection_status"


def llm_cost_projection_status_to_json(payload: Mapping[str, Any]) -> str:
    current = _money(payload.get("current_spend", payload.get("spend")))
    budget = _money(payload.get("reserved_budget", payload.get("budget")))
    projected = _money(payload.get("projected_spend", payload.get("projection", current)))
    remaining = round(budget - current, 2) if budget else 0.0
    overrun = round(max(projected - budget, 0.0), 2) if budget else 0.0
    utilization = round(projected / budget, 4) if budget else 0.0
    warning = _float(payload.get("warning_projected_overrun"), 0.0)
    critical = _float(payload.get("critical_projected_overrun"), 0.2)
    status = "healthy"
    if budget and utilization >= 1 + critical:
        status = "critical"
    elif budget and (overrun > warning or utilization >= 1.0):
        status = "warning"
    drivers = [_driver(row, index) for index, row in enumerate(list_of_maps(payload.get("drivers") or payload.get("top_cost_drivers") or payload.get("rows")), start=1)]
    drivers.sort(key=lambda row: (-row["projected_cost"], row["model"], row["profile"], row["stage"]))
    max_drivers = int_or_zero(payload.get("max_drivers", 5)) or 5
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {"status": status, "current_spend": current, "reserved_budget": budget, "projected_spend": projected, "remaining_budget": remaining, "projected_overrun": overrun, "projected_budget_utilization": utilization},
        "top_cost_drivers": drivers[:max_drivers],
        "metadata": source_metadata(payload),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _driver(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    return {"model": _text(item.get("model") or f"model-{index}"), "profile": _text(item.get("profile") or "default"), "stage": _text(item.get("stage") or "unknown"), "projected_cost": _money(item.get("projected_cost", item.get("cost")))}


def _money(value: Any) -> float:
    return round(max(0.0, float_or_zero(value)), 2)


def _float(value: Any, default: float) -> float:
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return default


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""

