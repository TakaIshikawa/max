"""JSON API renderer for run budget checkpoint status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from max.api._renderer_utils import float_or_zero, list_of_maps, parse_datetime, source_metadata

SCHEMA_VERSION = "max.api.run_budget_checkpoint_status.v1"
KIND = "max.api.run_budget_checkpoint_status"
RANK = {"critical": 0, "warning": 1, "healthy": 2}


def run_budget_checkpoint_status_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    checked_as_of = parse_datetime(as_of) or parse_datetime(payload.get("as_of"))
    rows = [_row(item, index) for index, item in enumerate(list_of_maps(payload.get("checkpoints") or payload.get("rows")), start=1)]
    rows.sort(key=lambda row: (RANK[row["status"]], row["stage"], row["checkpoint_id"]))
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "as_of": checked_as_of.isoformat().replace("+00:00", "Z") if checked_as_of else None, "summary": _summary(rows), "stage_rollups": _rollups(rows), "checkpoints": rows, "actions": _actions(rows), "metadata": source_metadata(payload)}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _row(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    reserved_tokens = float_or_zero(item.get("reserved_tokens"))
    used_tokens = float_or_zero(item.get("used_tokens"))
    reserved_cost = float_or_zero(item.get("reserved_cost"))
    actual_cost = float_or_zero(item.get("actual_cost"))
    hard = float_or_zero(item.get("hard_limit"))
    soft = float_or_zero(item.get("soft_limit"))
    token_ratio = used_tokens / reserved_tokens if reserved_tokens else 0.0
    cost_ratio = actual_cost / reserved_cost if reserved_cost else 0.0
    breached_hard = bool((hard and (used_tokens > hard or actual_cost > hard)) or item.get("hard_limit_breached"))
    breached_soft = bool((soft and (used_tokens > soft or actual_cost > soft)) or item.get("soft_limit_breached"))
    high_burn = token_ratio >= 0.9 or cost_ratio >= 0.9
    status = "critical" if breached_hard else ("warning" if breached_soft or high_burn else "healthy")
    return {"stage": str(item.get("stage") or "unknown"), "checkpoint_id": str(item.get("checkpoint_id") or item.get("id") or f"checkpoint-{index}"), "reserved_tokens": reserved_tokens, "used_tokens": used_tokens, "reserved_cost": reserved_cost, "actual_cost": actual_cost, "hard_limit": hard, "soft_limit": soft, "remaining_tokens": reserved_tokens - used_tokens, "remaining_cost": round(reserved_cost - actual_cost, 4), "checked_at": item.get("checked_at"), "status": status}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"status": "critical" if any(row["status"] == "critical" for row in rows) else ("warning" if any(row["status"] == "warning" for row in rows) else "healthy"), "checkpoint_count": len(rows), "critical_count": sum(1 for row in rows if row["status"] == "critical"), "warning_count": sum(1 for row in rows if row["status"] == "warning"), "remaining_tokens": sum(row["remaining_tokens"] for row in rows), "remaining_cost": round(sum(row["remaining_cost"] for row in rows), 4)}


def _rollups(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    stages = sorted({row["stage"] for row in rows})
    return [{"stage": stage, "checkpoint_count": sum(1 for row in rows if row["stage"] == stage), "used_tokens": sum(row["used_tokens"] for row in rows if row["stage"] == stage), "actual_cost": round(sum(row["actual_cost"] for row in rows if row["stage"] == stage), 4), "status": _summary([row for row in rows if row["stage"] == stage])["status"]} for stage in stages]


def _actions(rows: list[dict[str, Any]]) -> list[str]:
    actions = []
    if any(row["status"] == "critical" for row in rows):
        actions.append("stop the run and raise or rebalance the hard budget limit")
    if any(row["status"] == "warning" for row in rows):
        actions.append("review soft-limit burn before advancing to the next checkpoint")
    return actions
