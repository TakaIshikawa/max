"""Generate deterministic publisher retry policy tuning plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, number, summary

SCHEMA_VERSION = "max.spec.publisher_retry_policy_tuning_plan.v1"
KIND = "max.spec.publisher_retry_policy_tuning_plan"


def generate_publisher_retry_policy_tuning_plan(spec_like: Any) -> dict[str, Any]:
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    hints = _hints(spec)
    patterns = _patterns(hints.get("retry_history") or hints.get("events") or spec.get("retry_history") or spec.get("events"))

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(ctx, retry_pattern_count=len(patterns), recommendation_count=len(patterns)),
        "retry_patterns": patterns,
        "policy_recommendations": _recommendations(patterns),
        "validation_metrics": _validation_metrics(),
        "evidence_references": ctx["evidence_references"],
    }


def _patterns(value: Any) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for item in value if isinstance(value, list) else []:
        if not isinstance(item, dict):
            continue
        target = compact(item.get("target_type") or item.get("target")) or "unknown"
        reason = _reason(item)
        key = (target, reason)
        row = grouped.setdefault(key, {"target_type": target, "failure_reason": reason, "event_count": 0, "attempts": 0})
        row["event_count"] += 1
        row["attempts"] += int(number(item.get("attempts") or item.get("attempt_count")) or 1)
    rows = [
        {
            "id": f"PRP{index}",
            "target_type": row["target_type"],
            "failure_reason": row["failure_reason"],
            "event_count": row["event_count"],
            "average_attempts": round(row["attempts"] / row["event_count"], 2) if row["event_count"] else 0.0,
            "classification": _classification(row["failure_reason"]),
        }
        for index, row in enumerate(grouped.values(), start=1)
    ]
    return sorted(rows, key=lambda row: (_classification_rank(row["classification"]), row["target_type"].casefold(), row["failure_reason"].casefold()))


def _recommendations(patterns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    recommendations: list[dict[str, Any]] = []
    for pattern in patterns:
        if pattern["classification"] == "auth":
            action = "Reduce max attempts, shorten dead-letter threshold, and require credential repair before retry resume."
            interval = "long pause after first failure"
            max_attempts = 2
        elif pattern["classification"] == "network":
            action = "Use exponential backoff with jitter and allow more attempts before dead-lettering."
            interval = "exponential backoff with jitter"
            max_attempts = 6
        else:
            action = "Keep standard retry cadence while collecting more failure detail."
            interval = "standard backoff"
            max_attempts = 3
        recommendations.append({"id": f"PRR{len(recommendations) + 1}", "target_type": pattern["target_type"], "failure_reason": pattern["failure_reason"], "retry_interval": interval, "max_attempts": max_attempts, "dead_letter_threshold": max(1, max_attempts - 1), "action": action})
    return recommendations


def _validation_metrics() -> list[dict[str, str]]:
    return [
        {"id": "PRM1", "name": "publish_success_after_retry", "target": "improves for transient failures"},
        {"id": "PRM2", "name": "auth_failure_retry_waste", "target": "decreases after credential gating"},
        {"id": "PRM3", "name": "dead_letter_accuracy", "target": "dead-lettered events have actionable reason labels"},
    ]


def _reason(item: dict[str, Any]) -> str:
    return compact(item.get("failure_reason") or item.get("reason") or item.get("error_type")).casefold() or "unknown"


def _classification(reason: str) -> str:
    if "auth" in reason or "credential" in reason or "permission" in reason:
        return "auth"
    if "network" in reason or "timeout" in reason or "transient" in reason:
        return "network"
    return "other"


def _classification_rank(value: str) -> int:
    return {"auth": 0, "network": 1, "other": 2}.get(value, 3)


def _hints(spec: dict[str, Any]) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    hints = metadata.get("publisher_retry_policy_tuning")
    return hints if isinstance(hints, dict) else {}
