"""Run cost attribution export report."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any

SCHEMA_VERSION = "max.run_cost_attribution_report.v1"
KIND = "max.run_cost_attribution_report"


def generate_run_cost_attribution_report(payload: Mapping[str, Any] | Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    records = _records(payload)
    total_cost = round(sum(row["cost"] for row in records), 4)
    budget = _float(payload.get("budget", payload.get("cost_budget"))) if isinstance(payload, Mapping) else 0.0
    warnings = [row["warning"] for row in records if row["warning"]]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "record_count": len(records),
            "total_cost": total_cost,
            "budget": budget,
            "budget_variance": round(total_cost - budget, 4) if budget else 0.0,
            "unknown_cost_count": len(warnings),
        },
        "stage_rows": _group(records, "stage", total_cost),
        "profile_rows": _group(records, "profile", total_cost),
        "idea_rows": _group(records, "idea_id", total_cost),
        "top_cost_drivers": _top(records, total_cost),
        "budget_variance": {"budget": budget, "actual_cost": total_cost, "variance": round(total_cost - budget, 4) if budget else 0.0, "variance_rate": _rate(total_cost - budget, budget) if budget else 0.0},
        "warnings": warnings,
        "recommendations": _recommendations(records, total_cost, budget, warnings),
    }


def _records(payload: Mapping[str, Any] | Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(payload, Mapping):
        source = payload.get("records") if isinstance(payload.get("records"), list) else payload.get("costs")
    else:
        source = list(payload)
    rows = [_record(item, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    rows.sort(key=lambda row: (-row["cost"], row["stage"], row["profile"], row["idea_id"]))
    return rows


def _record(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    raw_cost = item.get("cost", item.get("amount", item.get("actual_cost")))
    cost = _float(raw_cost)
    warning = "" if raw_cost not in (None, "") and cost > 0 else f"Missing or zero cost for record {index}"
    return {
        "stage": _text(item.get("stage") or item.get("pipeline_stage")) or "unknown-stage",
        "profile": _text(item.get("profile") or item.get("persona")) or "unknown-profile",
        "idea_id": _text(item.get("idea_id") or item.get("idea") or item.get("id")) or "unknown-idea",
        "cost_type": _text(item.get("cost_type") or item.get("type")) or "unknown-cost",
        "cost": cost,
        "warning": warning,
    }


def _group(records: list[dict[str, Any]], field: str, total_cost: float) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        grouped[row[field]].append(row)
    rows = [{"name": name, "cost": round(sum(item["cost"] for item in items), 4), "percentage": _rate(sum(item["cost"] for item in items), total_cost), "record_count": len(items)} for name, items in grouped.items()]
    rows.sort(key=lambda row: (-row["cost"], row["name"]))
    return rows


def _top(records: list[dict[str, Any]], total_cost: float) -> list[dict[str, Any]]:
    rows = [{key: row[key] for key in ("stage", "profile", "idea_id", "cost_type", "cost")} | {"percentage": _rate(row["cost"], total_cost)} for row in records]
    rows.sort(key=lambda row: (-row["cost"], row["stage"], row["profile"], row["idea_id"]))
    return rows[:5]


def _recommendations(records: list[dict[str, Any]], total_cost: float, budget: float, warnings: list[str]) -> list[dict[str, Any]]:
    rows = []
    if budget and total_cost > budget:
        rows.append({"type": "budget_overrun", "action": "Reduce or cap spending in the highest-cost stage"})
    if records:
        top = _group(records, "stage", total_cost)[0]
        rows.append({"type": "stage_optimization", "stage": top["name"], "action": "Review prompts, retries, and external calls for the highest-cost stage"})
    if warnings:
        rows.append({"type": "cost_data_quality", "action": "Backfill missing cost attribution values"})
    return rows


def _rate(numerator: float, denominator: float) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _float(value: Any) -> float:
    try:
        return round(max(float(value or 0), 0.0), 4)
    except (TypeError, ValueError):
        return 0.0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
