"""JSON API renderer for pipeline budget burn rate status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import float_or_zero, int_or_zero, source_metadata

SCHEMA_VERSION = "max.api.budget_burn_rate_status.v1"
KIND = "max.api.budget_burn_rate_status"
SEVERITY_RANK = {"critical": 0, "warn": 1, "ok": 2}


def budget_burn_rate_status_to_json(payload: Mapping[str, Any]) -> str:
    rows = _rows(payload)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(rows),
        "stages": rows,
        "metadata": source_metadata(payload, stage_count=len(rows)),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("stages") if isinstance(payload.get("stages"), list) else payload.get("rows")
    rows = [_row(item, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    return sorted(rows, key=lambda row: (SEVERITY_RANK[row["severity"]], -row["projected_overrun_total"], row["stage"]))


def _row(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    progress = _progress(item)
    planned_tokens = max(0, int_or_zero(item.get("planned_tokens", item.get("token_budget"))))
    actual_tokens = max(0, int_or_zero(item.get("actual_tokens", item.get("tokens_used"))))
    planned_cost = max(0.0, float_or_zero(item.get("planned_cost_usd", item.get("cost_budget_usd"))))
    actual_cost = max(0.0, float_or_zero(item.get("actual_cost_usd", item.get("cost_usd"))))
    factor = 1 / progress if progress > 0 else 1.0
    projected_tokens = actual_tokens * factor
    projected_cost = actual_cost * factor
    token_overrun = max(projected_tokens - planned_tokens, 0.0)
    cost_overrun = max(projected_cost - planned_cost, 0.0)
    exhaustion = _exhaustion_progress(actual_tokens, planned_tokens, actual_cost, planned_cost, progress)
    severity = _severity(exhaustion)
    return {
        "stage": _text(item.get("stage") or item.get("name")) or f"stage-{index}",
        "run_progress_percent": round(progress * 100, 2),
        "planned_tokens": planned_tokens,
        "actual_tokens": actual_tokens,
        "projected_tokens": round(projected_tokens, 2),
        "planned_cost_usd": round(planned_cost, 4),
        "actual_cost_usd": round(actual_cost, 4),
        "projected_cost_usd": round(projected_cost, 4),
        "projected_token_overrun": round(token_overrun, 2),
        "projected_cost_overrun_usd": round(cost_overrun, 4),
        "projected_overrun_total": round(token_overrun + cost_overrun, 4),
        "projected_exhaustion_percent": round(exhaustion * 100, 2) if exhaustion else None,
        "severity": severity,
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "stage_count": len(rows),
        "total_planned_tokens": sum(row["planned_tokens"] for row in rows),
        "total_actual_tokens": sum(row["actual_tokens"] for row in rows),
        "total_projected_tokens": round(sum(row["projected_tokens"] for row in rows), 2),
        "total_planned_cost_usd": round(sum(row["planned_cost_usd"] for row in rows), 4),
        "total_actual_cost_usd": round(sum(row["actual_cost_usd"] for row in rows), 4),
        "total_projected_cost_usd": round(sum(row["projected_cost_usd"] for row in rows), 4),
        "total_projected_overrun": round(sum(row["projected_overrun_total"] for row in rows), 4),
        "highest_severity": min((row["severity"] for row in rows), key=lambda value: SEVERITY_RANK[value], default="ok"),
    }


def _progress(item: Mapping[str, Any]) -> float:
    raw = item.get("run_progress_percent", item.get("progress_percent", item.get("run_completion_percent")))
    progress = float_or_zero(raw)
    if progress > 1:
        progress /= 100
    return min(max(progress, 0.0), 1.0)


def _exhaustion_progress(actual_tokens: int, planned_tokens: int, actual_cost: float, planned_cost: float, progress: float) -> float | None:
    candidates = []
    if actual_tokens > 0 and planned_tokens > 0 and progress > 0:
        candidates.append(progress * planned_tokens / actual_tokens)
    if actual_cost > 0 and planned_cost > 0 and progress > 0:
        candidates.append(progress * planned_cost / actual_cost)
    return min(candidates) if candidates else None


def _severity(exhaustion: float | None) -> str:
    if exhaustion is None or exhaustion >= 1.0:
        return "ok"
    return "critical" if exhaustion <= 0.8 else "warn"


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
