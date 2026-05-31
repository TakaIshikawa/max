"""Generate deterministic LLM budget reallocation plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, number, summary

SCHEMA_VERSION = "max.spec.llm_budget_reallocation_plan.v1"
KIND = "max.spec.llm_budget_reallocation_plan"


def generate_llm_budget_reallocation_plan(spec_like: Any) -> dict[str, Any]:
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    hints = _hints(spec)
    allocations = _allocations(hints.get("allocations") or spec.get("allocations"))
    pressure_points = _pressure_points(allocations)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(ctx, allocation_count=len(allocations), pressure_point_count=len(pressure_points), recommendation_count=len(_recommendations(allocations))),
        "current_allocation_summary": allocations,
        "pressure_points": pressure_points,
        "recommended_reallocations": _recommendations(allocations),
        "guardrails": _guardrails(),
        "validation_metrics": _validation_metrics(),
        "rollback_triggers": _rollback_triggers(),
        "evidence_references": ctx["evidence_references"],
    }


def _allocations(value: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(value if isinstance(value, list) else [], start=1):
        if not isinstance(item, dict):
            continue
        budget_tokens = number(item.get("budget_tokens") or item.get("reserved_tokens")) or 0.0
        used_tokens = number(item.get("used_tokens") or item.get("consumed_tokens")) or 0.0
        budget_cost = number(item.get("budget_cost") or item.get("reserved_cost")) or 0.0
        used_cost = number(item.get("used_cost") or item.get("consumed_cost")) or 0.0
        output_value = number(item.get("output_value") or item.get("value_score")) or 0.0
        token_utilization = round(used_tokens / budget_tokens, 4) if budget_tokens else 0.0
        cost_utilization = round(used_cost / budget_cost, 4) if budget_cost else 0.0
        rows.append(
            {
                "id": compact(item.get("id")) or f"LBA{index}",
                "profile": compact(item.get("profile")) or "default",
                "stage": compact(item.get("stage")) or "unspecified",
                "model": compact(item.get("model")) or "unspecified",
                "provider": compact(item.get("provider")) or "unspecified",
                "budget_tokens": budget_tokens,
                "used_tokens": used_tokens,
                "budget_cost": budget_cost,
                "used_cost": used_cost,
                "output_value": output_value,
                "token_utilization": token_utilization,
                "cost_utilization": cost_utilization,
                "status": _status(token_utilization, cost_utilization, output_value, budget_tokens, budget_cost),
            }
        )
    return sorted(rows, key=lambda row: (_status_rank(row["status"]), row["profile"], row["stage"], row["provider"], row["model"]))


def _pressure_points(allocations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    for index, item in enumerate([row for row in allocations if row["status"] in {"over_budget", "under_utilized", "zero_budget"}], start=1):
        points.append({"id": f"LBP{index}", "allocation_id": item["id"], "status": item["status"], "stage": item["stage"], "profile": item["profile"], "severity": "high" if item["status"] in {"over_budget", "zero_budget"} else "medium"})
    return points


def _recommendations(allocations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    recommendations: list[dict[str, Any]] = []
    for item in allocations:
        if item["status"] == "over_budget":
            action = "Increase token or cost allocation only if output value remains above threshold; otherwise reduce retries or move to cheaper model."
        elif item["status"] == "under_utilized":
            action = "Return unused allocation to shared pool or reassign to higher-pressure stages."
        elif item["status"] == "zero_budget":
            action = "Set an explicit starter budget before the next run to avoid untracked usage."
        else:
            continue
        recommendations.append({"id": f"LBR{len(recommendations) + 1}", "allocation_id": item["id"], "action": action, "deterministic_order": len(recommendations) + 1})
    return recommendations


def _guardrails() -> list[dict[str, str]]:
    return [
        {"id": "LBG1", "name": "provider_cap", "description": "Do not increase a provider allocation above approved spend cap."},
        {"id": "LBG2", "name": "quality_floor", "description": "Do not cut budget for stages whose output value is above threshold without owner approval."},
        {"id": "LBG3", "name": "zero_budget_control", "description": "Block production usage for stages without explicit token and cost budgets."},
    ]


def _validation_metrics() -> list[dict[str, str]]:
    return [
        {"id": "LBM1", "name": "budget_overrun_rate", "target": "<= agreed tolerance"},
        {"id": "LBM2", "name": "underutilized_budget_rate", "target": "decreasing week over week"},
        {"id": "LBM3", "name": "output_value_per_cost", "target": "stable or improving"},
    ]


def _rollback_triggers() -> list[dict[str, str]]:
    return [
        {"id": "LBB1", "name": "quality_drop", "action": "Restore previous allocation if acceptance or approval quality drops below threshold."},
        {"id": "LBB2", "name": "spend_spike", "action": "Rollback if provider spend spikes after reallocation."},
    ]


def _status(token_utilization: float, cost_utilization: float, output_value: float, budget_tokens: float, budget_cost: float) -> str:
    if budget_tokens == 0 and budget_cost == 0:
        return "zero_budget"
    if token_utilization > 1.0 or cost_utilization > 1.0:
        return "over_budget"
    if max(token_utilization, cost_utilization) < 0.4 or output_value < 0.3:
        return "under_utilized"
    return "balanced"


def _status_rank(value: str) -> int:
    return {"over_budget": 0, "zero_budget": 1, "under_utilized": 2, "balanced": 3}.get(value, 4)


def _hints(spec: dict[str, Any]) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    hints = metadata.get("llm_budget_reallocation")
    return hints if isinstance(hints, dict) else {}
