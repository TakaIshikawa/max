"""JSON API renderer for LLM budget burn rate status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import float_or_zero, int_or_zero, source_metadata

SCHEMA_VERSION = "max.api.llm_budget_burn_rate_status.v1"
KIND = "max.api.llm_budget_burn_rate_status"


def llm_budget_burn_rate_status_to_json(payload: Mapping[str, Any]) -> str:
    rows = _rows(payload)
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(rows), "rows": rows, "metadata": source_metadata(payload, budget_count=len(rows))}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("budgets") if isinstance(payload.get("budgets"), list) else payload.get("items")
    rows = [_row(item) for item in source if isinstance(item, Mapping)] if isinstance(source, list) else []
    return sorted(rows, key=lambda row: (not row["at_risk"], -row["projected_ratio"], row["provider"], row["model"], row["profile"]))


def _row(item: Mapping[str, Any]) -> dict[str, Any]:
    tokens = max(0, int_or_zero(item.get("tokens_used")))
    token_budget = max(0, int_or_zero(item.get("token_budget")))
    cost = max(0.0, float_or_zero(item.get("cost_usd")))
    cost_budget = max(0.0, float_or_zero(item.get("cost_budget_usd")))
    elapsed = max(0.0, float_or_zero(item.get("elapsed_window_minutes")))
    total = max(0.0, float_or_zero(item.get("total_window_minutes")))
    projection_factor = total / elapsed if elapsed else 1.0
    token_ratio = tokens / token_budget if token_budget else (1.0 if tokens else 0.0)
    cost_ratio = cost / cost_budget if cost_budget else (1.0 if cost else 0.0)
    projected_ratio = max(token_ratio * projection_factor, cost_ratio * projection_factor)
    return {"provider": _bucket(item.get("provider"), "unknown"), "model": _bucket(item.get("model"), "unknown"), "profile": _bucket(item.get("profile"), "default"), "tokens_used": tokens, "token_budget": token_budget, "cost_usd": round(cost, 4), "cost_budget_usd": round(cost_budget, 4), "elapsed_window_minutes": round(elapsed, 4), "total_window_minutes": round(total, 4), "token_burn_ratio": round(token_ratio, 4), "cost_burn_ratio": round(cost_ratio, 4), "projected_ratio": round(projected_ratio, 4), "at_risk": projected_ratio > 1.0}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"status": "at_risk" if any(row["at_risk"] for row in rows) else "within_budget", "total_tokens_used": sum(row["tokens_used"] for row in rows), "total_cost_usd": round(sum(row["cost_usd"] for row in rows), 4), "at_risk_count": sum(1 for row in rows if row["at_risk"]), "highest_projected_ratio": max((row["projected_ratio"] for row in rows), default=0.0)}


def _bucket(value: Any, default: str) -> str:
    text = " ".join(str(value).strip().split()) if value is not None else ""
    return (text or default).lower().replace(" ", "_")
