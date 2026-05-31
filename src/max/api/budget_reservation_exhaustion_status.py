"""JSON API renderer for budget reservation exhaustion status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import float_or_zero, source_metadata

SCHEMA_VERSION = "max.api.budget_reservation_exhaustion_status.v1"
KIND = "max.api.budget_reservation_exhaustion_status"


def budget_reservation_exhaustion_status_to_json(
    payload: Mapping[str, Any],
    *,
    warning_remaining_ratio: float | None = None,
    critical_remaining_ratio: float | None = None,
) -> str:
    warn = _ratio(warning_remaining_ratio if warning_remaining_ratio is not None else payload.get("warning_remaining_ratio"), 0.2)
    critical = _ratio(critical_remaining_ratio if critical_remaining_ratio is not None else payload.get("critical_remaining_ratio"), 0.05)
    rows = [_row(item, warn, critical) for item in _items(payload)]
    rows.sort(key=lambda row: (row["severity_rank"], row["remaining_budget"], row["stage"], row["profile"]))
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(rows, warn, critical), "rows": rows, "metadata": source_metadata(payload, group_count=len(rows))}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    source = payload.get("reservations") if isinstance(payload.get("reservations"), list) else payload.get("budgets")
    return [item for item in source if isinstance(item, Mapping)] if isinstance(source, list) else []


def _row(item: Mapping[str, Any], warn: float, critical: float) -> dict[str, Any]:
    budget = max(
        0.0,
        float_or_zero(item.get("budget", item.get("budget_limit", item.get("total_budget")))),
    )
    reserved_raw = float_or_zero(item.get("reserved", item.get("reserved_budget")))
    spent_raw = float_or_zero(item.get("spent", item.get("spent_budget")))
    invalid = reserved_raw < 0 or spent_raw < 0 or budget <= 0
    reserved = max(0.0, reserved_raw)
    spent = max(0.0, spent_raw)
    remaining = round(budget - max(reserved, spent), 4)
    remaining_ratio = round(remaining / budget, 4) if budget else 0.0
    over_reserved = reserved > budget
    severity = "warn" if invalid else "critical" if remaining_ratio <= critical or over_reserved else "warn" if remaining_ratio <= warn else "healthy"
    return {"stage": _text(item.get("stage") or item.get("pipeline_stage"), "unspecified"), "profile": _text(item.get("profile") or item.get("profile_id"), "unspecified"), "budget": budget, "reserved_budget": reserved, "spent_budget": spent, "remaining_budget": remaining, "spent_ratio": round(spent / budget, 4) if budget else 0.0, "reserved_ratio": round(reserved / budget, 4) if budget else 0.0, "remaining_ratio": remaining_ratio, "over_reserved": over_reserved, "invalid_budget": invalid, "severity": severity, "severity_rank": {"critical": 0, "warn": 1, "healthy": 2}[severity]}


def _summary(rows: list[dict[str, Any]], warn: float, critical: float) -> dict[str, Any]:
    severity = "critical" if any(row["severity"] == "critical" for row in rows) else "warn" if any(row["severity"] == "warn" for row in rows) else "healthy"
    return {"severity": severity, "group_count": len(rows), "remaining_budget": round(sum(row["remaining_budget"] for row in rows), 4), "over_reserved_count": sum(1 for row in rows if row["over_reserved"]), "invalid_budget_count": sum(1 for row in rows if row["invalid_budget"]), "warning_remaining_ratio": warn, "critical_remaining_ratio": critical}


def _ratio(value: Any, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    if number > 1:
        number /= 100
    return round(min(max(number, 0.0), 1.0), 4)


def _text(value: Any, default: str) -> str:
    return " ".join(str(value).strip().split()) if value not in (None, "") else default
