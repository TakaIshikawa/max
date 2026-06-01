"""JSON API renderer for pipeline run cost attribution status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from max.api._renderer_utils import float_or_zero, list_of_maps, parse_datetime, source_metadata

SCHEMA_VERSION = "max.api.pipeline_run_cost_attribution_status.v1"
KIND = "max.api.pipeline_run_cost_attribution_status"


def pipeline_run_cost_attribution_status_to_json(payload: Mapping[str, Any], *, as_of: datetime | str | None = None) -> str:
    checked_at = parse_datetime(as_of) or parse_datetime(payload.get("as_of")) or datetime.now(timezone.utc)
    rows = [_row(row, i) for i, row in enumerate(_cost_rows(payload), start=1)]
    rows = sorted(rows, key=lambda row: (-row["cost_usd"], row["run_id"].casefold(), row["stage"].casefold()))
    total = round(sum(row["cost_usd"] for row in rows), 2)
    unallocated = round(sum(row["cost_usd"] for row in rows if row["unallocated"]), 2)
    top = rows[0] if rows else None
    over = sum(1 for row in rows if row["over_budget"])
    status = "critical" if over else ("warning" if unallocated else "healthy")
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "as_of": _stamp(checked_at), "status": status, "summary": {"status": status, "run_count": len({row["run_id"] for row in rows}), "row_count": len(rows), "total_cost_usd": total, "unallocated_cost_usd": unallocated, "over_budget_count": over, "top_cost_driver": {"run_id": top["run_id"], "stage": top["stage"], "cost_usd": top["cost_usd"]} if top else None}, "attributions": rows, "metadata": source_metadata(payload)}, indent=2, sort_keys=True)


def _cost_rows(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    direct = list_of_maps(payload.get("costs") or payload.get("items") or payload.get("stages") or payload.get("rows"))
    if direct:
        return direct
    rows: list[Mapping[str, Any]] = []
    for run in list_of_maps(payload.get("runs")):
        run_id = _text(run.get("run_id") or run.get("run"))
        for stage in list_of_maps(run.get("stages") or run.get("costs") or run.get("items")):
            merged = dict(stage)
            if run_id and not merged.get("run_id"):
                merged["run_id"] = run_id
            rows.append(merged)
    return rows


def _row(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    cost = max(0.0, float_or_zero(item.get("cost_usd") or item.get("cost") or item.get("amount_usd")))
    budget = max(0.0, float_or_zero(item.get("budget_usd") or item.get("budget")))
    run_id = _text(item.get("run_id") or item.get("run")) or f"run-{index}"
    stage = _text(item.get("stage") or item.get("stage_name")) or "unknown"
    profile = _text(item.get("profile")) or None
    return {"run_id": run_id, "stage": stage, "model": _text(item.get("model")) or None, "profile": profile, "cost_usd": round(cost, 2), "budget_usd": round(budget, 2) if budget else None, "over_budget": bool(budget and cost > budget), "unallocated": not bool(profile or _text(item.get("cost_center") or item.get("owner"))), "cost_center": _text(item.get("cost_center") or item.get("owner")) or None}


def _stamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
