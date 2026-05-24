"""JSON API renderer for pipeline budget forecasts."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "max.api.pipeline_budget_forecast.v1"
KIND = "max.api.pipeline_budget_forecast"
STATUS_RANK = {"overrun": 0, "watch": 1, "safe": 2}


def pipeline_budget_forecast_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    remaining_tokens = _number(payload.get("remaining_tokens", payload.get("token_budget_remaining")))
    remaining_cost = _number(payload.get("remaining_cost", payload.get("cost_budget_remaining")))
    stages = _stages(payload, remaining_tokens, remaining_cost)
    totals = _totals(stages, remaining_tokens, remaining_cost)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(stages, totals),
        "projected_totals": totals,
        "stages": stages,
        "stage_risks": [row for row in stages if row["status"] != "safe"],
        "reservation_gap": {"tokens": max(totals["projected_tokens"] - remaining_tokens, 0), "cost": round(max(totals["projected_cost"] - remaining_cost, 0.0), 6)},
        "metadata": _metadata(payload, stages, as_of),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _stages(payload: Mapping[str, Any], remaining_tokens: float, remaining_cost: float) -> list[dict[str, Any]]:
    source = payload.get("stages") if isinstance(payload.get("stages"), list) else payload.get("forecast")
    rows = [_stage(item, index, remaining_tokens, remaining_cost) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    rows.sort(key=lambda row: (STATUS_RANK[row["status"]], -row["utilization_ratio"], row["stage"]))
    return rows


def _stage(item: Mapping[str, Any], index: int, remaining_tokens: float, remaining_cost: float) -> dict[str, Any]:
    tokens = int(_number(item.get("projected_tokens", item.get("tokens"))))
    cost = _number(item.get("projected_cost", item.get("cost")))
    token_ratio = _ratio(tokens, remaining_tokens)
    cost_ratio = _ratio(cost, remaining_cost)
    utilization = max(token_ratio, cost_ratio)
    status = "overrun" if (remaining_tokens and tokens > remaining_tokens) or (remaining_cost and cost > remaining_cost) else ("watch" if utilization >= 0.8 else "safe")
    return {"stage": _text(item.get("stage") or item.get("name")) or f"stage-{index}", "projected_tokens": tokens, "projected_cost": cost, "token_utilization_ratio": token_ratio, "cost_utilization_ratio": cost_ratio, "utilization_ratio": utilization, "status": status}


def _totals(stages: list[dict[str, Any]], remaining_tokens: float, remaining_cost: float) -> dict[str, Any]:
    tokens = sum(row["projected_tokens"] for row in stages)
    cost = round(sum(row["projected_cost"] for row in stages), 6)
    return {"remaining_tokens": int(remaining_tokens), "remaining_cost": remaining_cost, "projected_tokens": tokens, "projected_cost": cost, "token_utilization_ratio": _ratio(tokens, remaining_tokens), "cost_utilization_ratio": _ratio(cost, remaining_cost)}


def _summary(stages: list[dict[str, Any]], totals: dict[str, Any]) -> dict[str, Any]:
    if any(row["status"] == "overrun" for row in stages) or totals["token_utilization_ratio"] > 1 or totals["cost_utilization_ratio"] > 1:
        status = "overrun"
    elif any(row["status"] == "watch" for row in stages) or max(totals["token_utilization_ratio"], totals["cost_utilization_ratio"]) >= 0.8:
        status = "watch"
    else:
        status = "safe"
    return {"status": status, "stage_count": len(stages), "overrun_stage_count": sum(1 for row in stages if row["status"] == "overrun"), "watch_stage_count": sum(1 for row in stages if row["status"] == "watch")}


def _metadata(payload: Mapping[str, Any], stages: list[dict[str, Any]], as_of: str | datetime | None) -> dict[str, Any]:
    metadata = dict(payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {})
    return {**metadata, "source_schema_version": payload.get("schema_version"), "source_kind": payload.get("kind"), "as_of": _as_of(as_of), "stage_count": len(stages)}


def _ratio(value: float, limit: float) -> float:
    return round(max(value / limit, 0.0), 4) if limit > 0 else 0.0


def _number(value: Any) -> float:
    try:
        return round(max(float(value or 0), 0.0), 6)
    except (TypeError, ValueError):
        return 0.0


def _as_of(value: str | datetime | None) -> str | None:
    if isinstance(value, datetime):
        parsed = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return value


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
