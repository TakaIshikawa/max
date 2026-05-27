"""JSON API renderer for budget forecast status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import float_or_zero, int_or_zero, source_metadata

SCHEMA_VERSION = "max.api.budget_forecast_status.v1"
KIND = "max.api.budget_forecast_status"


def budget_forecast_status_to_json(payload: Mapping[str, Any]) -> str:
    rows = _rows(payload)
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(rows), "rows": rows, "metadata": source_metadata(payload, budget_count=len(rows))}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("budgets") if isinstance(payload.get("budgets"), list) else payload.get("items")
    rows = [_row(item) for item in source if isinstance(item, Mapping)] if isinstance(source, list) else []
    return sorted(rows, key=lambda row: (not row["overrun_risk"], -row["projected_overrun_usd"], row["profile"], row["provider"]))


def _row(item: Mapping[str, Any]) -> dict[str, Any]:
    spent = max(0.0, float_or_zero(item.get("spent_usd")))
    budget = max(0.0, float_or_zero(item.get("budget_usd")))
    projected = max(0.0, float_or_zero(item.get("projected_spend_usd")))
    overrun = max(0.0, projected - budget)
    return {"profile": _bucket(item.get("profile"), "default"), "provider": _bucket(item.get("provider"), "unknown"), "spent_usd": round(spent, 4), "budget_usd": round(budget, 4), "projected_spend_usd": round(projected, 4), "remaining_days": max(0, int_or_zero(item.get("remaining_days"))), "forecast_window_days": max(0, int_or_zero(item.get("forecast_window_days"))), "spend_ratio": round(min(spent / budget, 9999.0), 4) if budget else (1.0 if spent else 0.0), "projected_overrun_usd": round(overrun, 4), "overrun_risk": projected > budget if budget else bool(projected)}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"status": "at_risk" if any(row["overrun_risk"] for row in rows) else "on_track", "total_spent_usd": round(sum(row["spent_usd"] for row in rows), 4), "total_budget_usd": round(sum(row["budget_usd"] for row in rows), 4), "projected_overrun_usd": round(sum(row["projected_overrun_usd"] for row in rows), 4), "at_risk_count": sum(1 for row in rows if row["overrun_risk"])}


def _bucket(value: Any, default: str) -> str:
    text = " ".join(str(value).strip().split()) if value is not None else ""
    return (text or default).lower().replace(" ", "_")
