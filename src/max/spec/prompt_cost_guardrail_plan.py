"""Generate deterministic prompt cost guardrail plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, number, summary

SCHEMA_VERSION = "max.spec.prompt_cost_guardrail_plan.v1"
KIND = "max.spec.prompt_cost_guardrail_plan"


def generate_prompt_cost_guardrail_plan(prompts: Any, budgets: Any, *, alert_threshold: float = 0.8) -> dict[str, Any]:
    if alert_threshold <= 0 or alert_threshold > 1:
        raise ValueError("alert_threshold must be greater than 0 and less than or equal to 1")

    ctx = context({})
    budget_rows = _budgets(budgets)
    prompt_rows = _prompts(prompts, budget_rows, alert_threshold)
    actions = _remediation_actions(prompt_rows)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(
            ctx,
            prompt_count=len(prompt_rows),
            budget_count=len(budget_rows),
            guarded_prompt_count=sum(1 for item in prompt_rows if item["status"] in {"alert", "blocked"}),
            alert_threshold=alert_threshold,
        ),
        "budget_matches": prompt_rows,
        "remediation_actions": actions,
        "guardrails": _guardrails(),
        "owner_review": _owner_review(prompt_rows),
        "evidence_references": ctx["evidence_references"],
    }


def _prompts(value: Any, budgets: list[dict[str, Any]], alert_threshold: float) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(value if isinstance(value, list) else [], start=1):
        if not isinstance(item, dict):
            continue
        prompt_id = compact(item.get("prompt_id") or item.get("id")) or f"prompt_{index}"
        owner = compact(item.get("owner")) or "prompt_owner"
        budget = _match_budget(item, budgets)
        projected_spend = max(number(item.get("projected_spend") or item.get("cost") or item.get("spend")) or 0.0, 0.0)
        cost_cap = budget["cost_cap"] if budget else max(number(item.get("cost_cap") or item.get("budget")) or 0.0, 0.0)
        utilization = round(projected_spend / cost_cap, 4) if cost_cap else 0.0
        rows.append(
            {
                "id": f"PCG{index}",
                "prompt_id": prompt_id,
                "family": compact(item.get("family")) or "default",
                "model": compact(item.get("model")) or "unspecified",
                "owner": owner,
                "budget_id": budget["budget_id"] if budget else None,
                "budget_key": budget["budget_key"] if budget else None,
                "projected_spend": projected_spend,
                "cost_cap": cost_cap,
                "utilization": utilization,
                "status": _status(projected_spend, cost_cap, utilization, alert_threshold),
            }
        )
    return sorted(rows, key=lambda row: (-row["projected_spend"], row["prompt_id"].casefold(), row["model"].casefold()))


def _budgets(value: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(value if isinstance(value, list) else [], start=1):
        if not isinstance(item, dict):
            continue
        prompt_id = compact(item.get("prompt_id") or item.get("prompt"))
        family = compact(item.get("family"))
        model = compact(item.get("model"))
        rows.append(
            {
                "budget_id": compact(item.get("budget_id") or item.get("id")) or f"budget_{index}",
                "budget_key": prompt_id or family or model or "default",
                "prompt_id": prompt_id,
                "family": family,
                "model": model,
                "cost_cap": max(number(item.get("cost_cap") or item.get("cap") or item.get("budget")) or 0.0, 0.0),
            }
        )
    return rows


def _match_budget(prompt: dict[str, Any], budgets: list[dict[str, Any]]) -> dict[str, Any] | None:
    prompt_id = compact(prompt.get("prompt_id") or prompt.get("id"))
    family = compact(prompt.get("family"))
    model = compact(prompt.get("model"))
    for key, value in (("prompt_id", prompt_id), ("family", family), ("model", model)):
        if value:
            match = next((budget for budget in budgets if budget[key].casefold() == value.casefold()), None)
            if match:
                return match
    return next((budget for budget in budgets if budget["budget_key"] == "default"), None)


def _remediation_actions(prompts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for prompt in prompts:
        if prompt["status"] == "healthy":
            continue
        action = "Block production execution, enforce hard cost cap, throttle retries, and require owner review." if prompt["status"] == "blocked" else "Add spend alert, lower max tokens, throttle noncritical traffic, and schedule owner review."
        actions.append(
            {
                "id": f"PCA{len(actions) + 1}",
                "prompt_id": prompt["prompt_id"],
                "budget_id": prompt["budget_id"],
                "owner": prompt["owner"],
                "severity": "critical" if prompt["status"] == "blocked" else "warning",
                "projected_spend": prompt["projected_spend"],
                "action": action,
            }
        )
    return actions


def _guardrails() -> list[dict[str, str]]:
    return [
        {"id": "PCG1", "name": "cost_cap", "description": "Every prompt has an explicit cost cap before production use."},
        {"id": "PCG2", "name": "alert", "description": "Alert owners when projected spend reaches the configured threshold."},
        {"id": "PCG3", "name": "throttle", "description": "Throttle noncritical prompt traffic before hard caps are exceeded."},
    ]


def _owner_review(prompts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    owners = sorted({prompt["owner"] for prompt in prompts if prompt["status"] in {"alert", "blocked"}}, key=str.casefold)
    return [{"id": f"PCR{index}", "owner": owner, "action": "Review prompt spend, mitigation, and cap exception request."} for index, owner in enumerate(owners, start=1)]


def _status(projected_spend: float, cost_cap: float, utilization: float, alert_threshold: float) -> str:
    if cost_cap == 0 and projected_spend > 0:
        return "blocked"
    if cost_cap and projected_spend > cost_cap:
        return "blocked"
    if utilization >= alert_threshold:
        return "alert"
    return "healthy"
