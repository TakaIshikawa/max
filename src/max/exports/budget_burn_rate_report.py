"""Budget burn rate export report."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable

SCHEMA_VERSION = "max.budget_burn_rate_report.v1"
KIND = "max.budget_burn_rate_report"
_STATUS_ORDER = {"overrun": 0, "watch": 1, "ok": 2}


def generate_budget_burn_rate_report(
    samples: Iterable[dict[str, Any]],
    *,
    default_budget: Any = 0,
    watch_ratio: float = 0.8,
) -> dict[str, Any]:
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for raw in samples:
        if not isinstance(raw, dict):
            continue
        key = (
            _text(raw.get("profile") or raw.get("profile_id") or raw.get("domain_profile")) or "default",
            _text(raw.get("stage") or raw.get("pipeline_stage") or raw.get("phase")) or "unknown-stage",
        )
        group = groups.setdefault(key, {"spend": 0.0, "budget": _float(default_budget), "times": []})
        group["spend"] += _float(raw.get("spend") or raw.get("amount") or raw.get("cost") or raw.get("cost_usd"))
        group["budget"] = _float(raw.get("budget") or raw.get("budget_amount") or raw.get("daily_budget") or group["budget"])
        seen = _timestamp(raw.get("timestamp") or raw.get("spent_at") or raw.get("created_at"))
        if seen is not None:
            group["times"].append(seen)

    rows = []
    for (profile, stage), group in groups.items():
        elapsed = _elapsed_hours(group["times"])
        total = round(group["spend"], 6)
        burn = round(total / elapsed, 6) if elapsed else 0.0
        projected = round(burn * 24, 6)
        budget = round(group["budget"], 6)
        remaining = round(budget - total, 6)
        rows.append(
            {
                "profile": profile,
                "pipeline_stage": stage,
                "sample_count": len(group["times"]) or 1,
                "total_spend": total,
                "elapsed_hours": elapsed,
                "burn_rate_per_hour": burn,
                "projected_daily_spend": projected,
                "budget": budget,
                "remaining_budget": remaining,
                "status": _status(projected, budget, watch_ratio),
            }
        )
    rows.sort(key=lambda row: (_STATUS_ORDER[row["status"]], row["profile"].casefold(), row["pipeline_stage"].casefold()))
    total_budget = round(sum(row["budget"] for row in rows), 6)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "status": rows[0]["status"] if rows else "ok",
            "group_count": len(rows),
            "total_spend": round(sum(row["total_spend"] for row in rows), 6),
            "projected_daily_spend": round(sum(row["projected_daily_spend"] for row in rows), 6),
            "budget": total_budget,
            "remaining_budget": round(total_budget - sum(row["total_spend"] for row in rows), 6),
        },
        "rows": rows,
    }


def _status(projected: float, budget: float, watch_ratio: float) -> str:
    if budget and projected > budget:
        return "overrun"
    if budget and projected >= budget * max(0.0, min(1.0, watch_ratio)):
        return "watch"
    return "ok"


def _elapsed_hours(times: list[datetime]) -> float:
    if len(times) < 2:
        return 1.0 if times else 0.0
    hours = (max(times) - min(times)).total_seconds() / 3600
    return round(max(hours, 1 / 3600), 6)


def _timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if value is None:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _float(value: Any) -> float:
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return 0.0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
