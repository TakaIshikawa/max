"""Generate deterministic synthesis queue drain plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, number, summary

SCHEMA_VERSION = "max.spec.synthesis_queue_drain_plan.v1"
KIND = "max.spec.synthesis_queue_drain_plan"


def generate_synthesis_queue_drain_plan(spec_like: Any) -> dict[str, Any]:
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    hints = _hints(spec)
    batches = _batches(hints.get("batches") or hints.get("queue") or spec.get("batches") or spec.get("queue"))
    stale = [item for item in batches if item["stale"]]

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(ctx, queued_batch_count=len(batches), stale_batch_count=len(stale), action=_action(batches)),
        "queue_inventory": batches,
        "priority_order": _priority_order(batches),
        "batching_strategy": _batching_strategy(batches),
        "budget_guardrails": _budget_guardrails(),
        "rate_limit_safeguards": _rate_limit_safeguards(),
        "verification_steps": _verification_steps(batches),
        "evidence_references": ctx["evidence_references"],
    }


def _batches(value: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(value if isinstance(value, list) else [], start=1):
        if not isinstance(item, dict):
            continue
        age_hours = float(number(item.get("age_hours") or item.get("queued_hours") or item.get("stale_hours")) or 0.0)
        priority = compact(item.get("priority")) or "normal"
        rows.append(
            {
                "id": compact(item.get("id") or item.get("batch_id")) or f"SQB{index}",
                "profile": compact(item.get("profile")) or "default",
                "priority": priority,
                "age_hours": age_hours,
                "item_count": int(number(item.get("item_count") or item.get("size") or item.get("queued_count")) or 0),
                "estimated_cost": float(number(item.get("estimated_cost") or item.get("cost")) or 0.0),
                "rate_limit_key": compact(item.get("rate_limit_key") or item.get("provider")) or "default",
                "stale": bool(item.get("stale")) or age_hours >= 24,
            }
        )
    return sorted(rows, key=lambda row: (-row["age_hours"], _priority_rank(row["priority"]), row["profile"].casefold(), row["id"].casefold()))


def _priority_order(batches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": f"SQO{index}",
            "batch_id": item["id"],
            "profile": item["profile"],
            "priority": item["priority"],
            "age_hours": item["age_hours"],
            "reason": "oldest stale batch first" if item["stale"] else "fresh batch held behind stale work",
        }
        for index, item in enumerate(batches, start=1)
    ]


def _batching_strategy(batches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not batches:
        return [{"id": "SQS1", "name": "no_action", "action": "Keep synthesis workers idle and validate that the queue is truly empty.", "max_items": 0}]
    return [
        {"id": "SQS1", "name": "stale_first", "action": "Drain stale batches in deterministic priority order before accepting new low-priority synthesis work.", "max_items": 25},
        {"id": "SQS2", "name": "profile_fairness", "action": "Alternate profiles after each drain slice when age and priority are tied.", "max_items": 25},
        {"id": "SQS3", "name": "fresh_followup", "action": "Drain remaining fresh batches only after stale backlog and budget checks clear.", "max_items": 50},
    ]


def _budget_guardrails() -> list[dict[str, str]]:
    return [
        {"id": "SQG1", "name": "daily_budget_cap", "description": "Stop drain slices before projected synthesis spend exceeds the approved daily cap."},
        {"id": "SQG2", "name": "per_profile_quota", "description": "Reserve enough budget for every active profile before increasing one profile's drain share."},
        {"id": "SQG3", "name": "cost_recheck", "description": "Recompute estimated cost after every slice and pause on unexpected spend growth."},
    ]


def _rate_limit_safeguards() -> list[dict[str, str]]:
    return [
        {"id": "SQR1", "name": "provider_window", "description": "Throttle drain workers by rate-limit key and current provider window usage."},
        {"id": "SQR2", "name": "retry_backoff", "description": "Back off failed synthesis batches instead of immediately requeueing them at the front."},
        {"id": "SQR3", "name": "concurrency_limit", "description": "Increase concurrency only while error rate and latency remain within threshold."},
    ]


def _verification_steps(batches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    steps = [
        {"id": "SQV1", "name": "queue_count_delta", "expected": "queued batch count decreases to zero or approved residual"},
        {"id": "SQV2", "name": "budget_and_rate_limit_audit", "expected": "no budget cap or provider window breach"},
    ]
    if not batches:
        steps.append({"id": "SQV3", "name": "empty_queue_validation", "expected": "queue scan, worker lag, and dead-letter checks all report no pending synthesis batches"})
    else:
        steps.append({"id": "SQV3", "name": "profile_completion_sample", "expected": "sample drained batches by profile and priority for synthesis output acceptance"})
    return steps


def _action(batches: list[dict[str, Any]]) -> str:
    return "no_action" if not batches else "drain_queue"


def _priority_rank(value: str) -> int:
    return {"critical": 0, "high": 1, "normal": 2, "medium": 2, "low": 3}.get(value.casefold(), 4)


def _hints(spec: dict[str, Any]) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    hints = metadata.get("synthesis_queue_drain")
    return hints if isinstance(hints, dict) else {}
