"""Generate deterministic webhook delivery reliability plans."""

from __future__ import annotations

from typing import Any


SCHEMA_VERSION = "max-webhook-delivery-reliability-plan/v1"
KIND = "max.spec.webhook_delivery_reliability_plan"


def generate_webhook_delivery_reliability_plan(spec_like: dict[str, Any] | None = None) -> dict[str, Any]:
    spec = spec_like if isinstance(spec_like, dict) else {}
    rows = _endpoint_rows(spec)
    actions = []
    for row in rows:
        if row["risk_score"] >= 3:
            actions.append({"endpoint_id": row["id"], "owner": row["owner"], "action": _action_for(row), "due_date": "next reliability review"})
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "endpoint_count": len(rows),
            "high_risk_count": sum(1 for row in rows if row["risk"] == "high"),
            "missing_retry_policy_count": sum(1 for row in rows if "missing-retry-policy" in row["risk_factors"]),
            "missing_owner_count": sum(1 for row in rows if "missing-owner" in row["risk_factors"]),
        },
        "endpoint_rows": rows,
        "reliability_actions": actions,
        "dead_letter_review": _dead_letter_review(spec, rows),
        "retry_policy": _retry_policy(spec),
    }


def render_webhook_delivery_reliability_plan_markdown(plan_or_spec: dict[str, Any] | None = None) -> str:
    plan = plan_or_spec if _is_plan(plan_or_spec) else generate_webhook_delivery_reliability_plan(plan_or_spec)
    lines = ["# Webhook Delivery Reliability Plan", "", f"Schema version: {plan['schema_version']}", "", "## Endpoint Reliability", ""]
    for row in plan["endpoint_rows"]:
        lines.append(f"- {row['id']}: {row['endpoint']} owner={row['owner']} failure_rate={row['failure_rate']} risk={row['risk']} factors={', '.join(row['risk_factors']) or 'none'}")
    lines.extend(["", "## Retry Actions", ""])
    if plan["reliability_actions"]:
        for action in plan["reliability_actions"]:
            lines.append(f"- {action['endpoint_id']}: {action['action']} by {action['owner']} due {action['due_date']}")
    else:
        lines.append("- No retry actions required.")
    dlq = plan["dead_letter_review"]
    lines.extend(["", "## Dead Letter Review", "", f"- Queue: {dlq['queue']}", f"- Owner: {dlq['owner']}", f"- Cadence: {dlq['cadence']}"])
    retry = plan["retry_policy"]
    lines.extend(["", "## Policy", "", f"- Attempts: {retry['attempts']}", f"- Backoff: {retry['backoff']}", f"- Timeout: {retry['timeout']}"])
    return "\n".join(lines).rstrip() + "\n"


def _endpoint_rows(spec: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for index, raw in enumerate(_raw_endpoints(spec), start=1):
        endpoint = _text(raw.get("endpoint") or raw.get("url") or raw.get("name")) or f"endpoint-{index}"
        owner = _text(raw.get("owner")) or "webhook_platform_owner"
        events = _values(raw.get("event_types") or raw.get("events"), ["all-events"])
        failure_rate = _number(raw.get("failure_rate") or raw.get("failure_percent"))
        has_retry = _bool(raw.get("retry_policy") or raw.get("retries") or raw.get("has_retry_policy"))
        factors: list[str] = []
        if failure_rate >= 5:
            factors.append("high-failure-rate")
        elif failure_rate >= 1:
            factors.append("elevated-failure-rate")
        if not has_retry:
            factors.append("missing-retry-policy")
        if not _text(raw.get("owner")):
            factors.append("missing-owner")
        if any("customer" in event.casefold() or "payment" in event.casefold() or "invoice" in event.casefold() for event in events):
            factors.append("customer-critical-event")
        score = (3 if failure_rate >= 5 else 1 if failure_rate >= 1 else 0) + (2 if not has_retry else 0) + (1 if not _text(raw.get("owner")) else 0) + (1 if "customer-critical-event" in factors else 0)
        rows.append({"id": "", "endpoint": endpoint, "owner": owner, "event_types": events, "failure_rate": f"{failure_rate:g}%", "dead_letter_queue": _text(raw.get("dead_letter_queue") or raw.get("dlq")) or "dead-letter-queue-required", "risk_factors": factors, "risk_score": score, "risk": "high" if score >= 4 else "medium" if score >= 2 else "low"})
    if not rows:
        rows.append({"id": "", "endpoint": "webhook-endpoint-intake", "owner": "webhook_platform_owner", "event_types": ["all-events"], "failure_rate": "0%", "dead_letter_queue": "dead-letter-queue-required", "risk_factors": ["missing-retry-policy", "missing-owner"], "risk_score": 3, "risk": "medium"})
    rows = sorted(rows, key=lambda row: (-row["risk_score"], row["endpoint"].casefold()))
    for index, row in enumerate(rows, start=1):
        row["id"] = f"WDR-{index:03d}"
    return rows


def _raw_endpoints(spec: dict[str, Any]) -> list[dict[str, Any]]:
    metadata = _dict(spec.get("metadata"))
    plan = _dict(metadata.get("webhook_delivery_reliability") or spec.get("webhook_delivery_reliability"))
    candidates = plan.get("endpoints") or metadata.get("webhook_endpoints") or spec.get("endpoints")
    return [item for item in candidates if isinstance(item, dict)] if isinstance(candidates, list) else []


def _action_for(row: dict[str, Any]) -> str:
    if "missing-retry-policy" in row["risk_factors"]:
        return "define retry policy and replay failed deliveries"
    if row["dead_letter_queue"] == "dead-letter-queue-required":
        return "configure dead letter queue and replay workflow"
    return "reduce failure rate and verify customer delivery"


def _dead_letter_review(spec: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, str]:
    review = _dict(_dict(spec.get("metadata")).get("dead_letter_review") or spec.get("dead_letter_review"))
    queue = _text(review.get("queue")) or next((row["dead_letter_queue"] for row in rows if row["dead_letter_queue"] != "dead-letter-queue-required"), "dead-letter-queue-required")
    return {"queue": queue, "owner": _text(review.get("owner")) or "webhook_platform_owner", "cadence": _text(review.get("cadence")) or "daily"}


def _retry_policy(spec: dict[str, Any]) -> dict[str, str]:
    policy = _dict(_dict(spec.get("metadata")).get("retry_policy") or spec.get("retry_policy"))
    return {"attempts": _text(policy.get("attempts")) or "3", "backoff": _text(policy.get("backoff")) or "exponential", "timeout": _text(policy.get("timeout")) or "30s"}


def _is_plan(value: dict[str, Any] | None) -> bool:
    return isinstance(value, dict) and value.get("kind") == KIND and "endpoint_rows" in value


def _bool(value: Any) -> bool:
    if isinstance(value, dict):
        return bool(value)
    if isinstance(value, bool):
        return value
    return _text(value).casefold() in {"true", "yes", "1", "enabled", "configured"}


def _number(value: Any) -> float:
    try:
        return float(str(value).strip().removesuffix("%"))
    except (TypeError, ValueError):
        return 0.0


def _values(value: Any, fallback: list[str]) -> list[str]:
    values = value if isinstance(value, list) else [value]
    result = [_text(item) for item in values if _text(item)]
    return result or fallback


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return " ".join(str(value).split()) if value is not None else ""
