"""Generate deterministic adapter rate-limit recovery plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, number, summary

SCHEMA_VERSION = "max.spec.adapter_rate_limit_recovery_plan.v1"
KIND = "max.spec.adapter_rate_limit_recovery_plan"


def generate_adapter_rate_limit_recovery_plan(spec_like: Any) -> dict[str, Any]:
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    hints = _hints(spec)
    adapters = _adapters(hints.get("adapters") or hints.get("incidents") or spec.get("adapters") or spec.get("incidents"))

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(
            ctx,
            adapter_count=len(adapters),
            highest_risk_adapter=adapters[0]["name"] if adapters else None,
            recommendation=_recommendation(adapters),
        ),
        "adapter_recovery_windows": adapters,
        "quota_conservation_steps": _quota_conservation_steps(adapters),
        "backoff_policy_checks": _backoff_policy_checks(adapters),
        "stakeholder_impact": _stakeholder_impact(adapters),
        "verification_gates": _verification_gates(adapters),
        "evidence_references": ctx["evidence_references"],
    }


def _adapters(value: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(value if isinstance(value, list) else [], start=1):
        if not isinstance(item, dict):
            continue
        remaining = _field_number(item, "remaining_quota", "quota_remaining", "remaining")
        limit = _field_number(item, "quota_limit", "limit", "capacity")
        reset_at = compact(item.get("reset_at") or item.get("reset_time") or item.get("quota_reset_at"))
        exhausted = bool(item.get("exhausted")) or remaining == 0
        degradation = compact(item.get("degradation") or item.get("status")).casefold()
        risk = _risk(remaining, limit, exhausted, degradation, reset_at)
        rows.append(
            {
                "id": compact(item.get("id") or item.get("adapter_id")) or f"ARL{index}",
                "name": compact(item.get("name") or item.get("adapter")) or f"adapter_{index}",
                "owner": compact(item.get("owner") or item.get("team")) or _owner_hint(risk),
                "risk": risk,
                "remaining_quota": float(remaining or 0.0),
                "quota_limit": float(limit or 0.0),
                "quota_utilization": _utilization(remaining, limit),
                "reset_at": reset_at or "unknown",
                "reset_time_known": bool(reset_at),
                "impact": compact(item.get("impact") or item.get("customer_impact")) or _impact(risk),
            }
        )
    return sorted(rows, key=lambda row: (_risk_rank(row["risk"]), row["name"].casefold(), row["id"].casefold()))


def _quota_conservation_steps(adapters: list[dict[str, Any]]) -> list[dict[str, str]]:
    if not adapters:
        return [{"id": "ARC1", "adapter_id": "none", "action": "Keep standard quota monitoring active until a rate-limit incident appears."}]
    steps: list[dict[str, str]] = []
    for adapter in adapters:
        if adapter["risk"] == "exhausted":
            action = "pause noncritical requests, serve cached responses, and reserve quota for recovery verification"
        elif adapter["risk"] == "high":
            action = "throttle optional traffic and prioritize customer-visible requests until reset"
        else:
            action = "keep degraded adapter traffic on reduced concurrency while monitoring quota burn"
        steps.append({"id": f"ARC{len(steps) + 1}", "adapter_id": adapter["id"], "owner": adapter["owner"], "action": action})
        if not adapter["reset_time_known"]:
            steps.append({"id": f"ARC{len(steps) + 1}", "adapter_id": adapter["id"], "owner": adapter["owner"], "action": "confirm provider quota reset time and update the recovery window"})
    return steps


def _backoff_policy_checks(adapters: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {"id": "ARB1", "name": "exponential_backoff_enabled", "target": "rate-limited requests use exponential backoff with jitter"},
        {"id": "ARB2", "name": "retry_budget_capped", "target": "retry attempts stop before quota conservation is breached"},
        {"id": "ARB3", "name": "reset_time_follow_up", "target": "unknown reset times have an owner and provider follow-up"} if any(not adapter["reset_time_known"] for adapter in adapters) else {"id": "ARB3", "name": "reset_window_tracked", "target": "all adapters have known reset windows"},
    ]


def _stakeholder_impact(adapters: list[dict[str, Any]]) -> list[dict[str, str]]:
    if not adapters:
        return [{"id": "ARS1", "adapter_id": "none", "impact": "No active stakeholder impact from rate limits."}]
    return [{"id": f"ARS{index}", "adapter_id": adapter["id"], "impact": adapter["impact"]} for index, adapter in enumerate(adapters, start=1)]


def _verification_gates(adapters: list[dict[str, Any]]) -> list[dict[str, str]]:
    target = "highest-risk adapter completes recovery smoke test after quota reset" if adapters else "quota dashboards remain below warning threshold"
    return [
        {"id": "ARV1", "name": "quota_available_after_reset", "target": target},
        {"id": "ARV2", "name": "no_retry_storm", "target": "retry volume remains within the capped backoff policy"},
        {"id": "ARV3", "name": "customer_visible_work_recovers", "target": "degraded workflows return to normal adapter success rate"},
    ]


def _recommendation(adapters: list[dict[str, Any]]) -> str:
    if not adapters:
        return "monitor"
    highest = adapters[0]
    if highest["risk"] == "exhausted":
        return f"hold noncritical traffic for {highest['name']} until quota reset is verified"
    if highest["risk"] == "high":
        return f"conserve quota for {highest['name']} and verify backoff policy"
    return "continue reduced-rate recovery monitoring"


def _risk(remaining: float | None, limit: float | None, exhausted: bool, degradation: str, reset_at: str) -> str:
    if exhausted or degradation in {"exhausted", "blocked"}:
        return "exhausted"
    utilization = _utilization(remaining, limit)
    if utilization >= 0.9 or degradation in {"partial", "degraded", "throttled"}:
        return "high"
    if not reset_at:
        return "medium"
    return "low"


def _risk_rank(value: str) -> int:
    return {"exhausted": 0, "high": 1, "medium": 2, "low": 3}.get(value, 4)


def _field_number(item: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        if key in item:
            return number(item.get(key))
    return None


def _utilization(remaining: float | None, limit: float | None) -> float:
    if remaining is None or limit is None or limit <= 0:
        return 0.0
    return round(max(0.0, min(1.0, (limit - remaining) / limit)), 4)


def _owner_hint(risk: str) -> str:
    return "adapter_lead" if risk in {"exhausted", "high"} else "adapter_owner"


def _impact(risk: str) -> str:
    if risk == "exhausted":
        return "adapter requests are blocked until quota recovers"
    if risk == "high":
        return "adapter throughput is partially degraded"
    return "adapter is under observation for rate-limit risk"


def _hints(spec: dict[str, Any]) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    hints = metadata.get("adapter_rate_limit_recovery")
    return hints if isinstance(hints, dict) else {}
