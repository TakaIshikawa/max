"""Budget stage spend export report."""

from __future__ import annotations

from typing import Any, Iterable

SCHEMA_VERSION = "max.budget_stage_spend_report.v1"
KIND = "max.budget_stage_spend_report"
_STATUS_RANK = {"breach": 0, "watch": 1, "ok": 2}


def generate_budget_stage_spend_report(
    records: Iterable[dict[str, Any]],
    *,
    total_budget: Any = None,
    spend_share_threshold: float = 0.4,
    absolute_cost_threshold: float = 100.0,
) -> dict[str, Any]:
    share_threshold = _ratio(spend_share_threshold)
    cost_threshold = _float(absolute_cost_threshold)
    groups: dict[tuple[str, str, str], dict[str, Any]] = {}
    for raw in records:
        if not isinstance(raw, dict):
            continue
        stage = _text(raw.get("stage") or raw.get("pipeline_stage") or raw.get("phase")) or "unknown-stage"
        profile = _text(raw.get("profile") or raw.get("domain_profile") or raw.get("profile_id")) or "default"
        model = _text(raw.get("model") or raw.get("model_name") or raw.get("llm_model")) or "unknown-model"
        group = groups.setdefault((stage, profile, model), {"tokens": 0, "cost": 0.0, "latest": ""})
        group["tokens"] += _int(raw.get("total_tokens") or raw.get("tokens") or _int(raw.get("input_tokens")) + _int(raw.get("output_tokens")))
        group["cost"] += _float(raw.get("total_cost") or raw.get("cost") or raw.get("usd_cost") or raw.get("cost_usd") or raw.get("amount"))
        seen_at = _text(raw.get("spent_at") or raw.get("completed_at") or raw.get("timestamp") or raw.get("created_at"))
        if seen_at > group["latest"]:
            group["latest"] = seen_at

    total_cost = round(sum(group["cost"] for group in groups.values()), 6)
    budget = _float(total_budget) or total_cost
    rows = []
    for (stage, profile, model), group in groups.items():
        cost = round(group["cost"], 6)
        share = round(cost / budget, 4) if budget else 0.0
        breaches = []
        if share_threshold and share > share_threshold:
            breaches.append("spend_share")
        if cost_threshold and cost > cost_threshold:
            breaches.append("absolute_cost")
        rows.append(
            {
                "stage": stage,
                "profile": profile,
                "model": model,
                "total_tokens": group["tokens"],
                "total_cost": cost,
                "budget_share": share,
                "threshold_breaches": breaches,
                "latest_spend_at": group["latest"] or None,
                "status": "breach" if breaches else ("watch" if share_threshold and share >= share_threshold * 0.8 else "ok"),
            }
        )
    rows.sort(key=lambda row: (_STATUS_RANK[row["status"]], row["stage"].casefold(), row["profile"].casefold(), row["model"].casefold()))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "row_count": len(rows),
            "total_tokens": sum(row["total_tokens"] for row in rows),
            "total_cost": total_cost,
            "total_budget": round(budget, 6),
            "breach_count": sum(1 for row in rows if row["status"] == "breach"),
            "spend_share_threshold": share_threshold,
            "absolute_cost_threshold": cost_threshold,
        },
        "rows": rows,
    }


def _ratio(value: Any) -> float:
    return min(1.0, max(0.0, _float(value)))


def _float(value: Any) -> float:
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return 0.0


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
