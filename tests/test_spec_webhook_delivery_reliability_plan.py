from __future__ import annotations

from max.spec import generate_webhook_delivery_reliability_plan, render_webhook_delivery_reliability_plan_markdown


def test_webhook_delivery_reliability_plan_prioritizes_risky_endpoints() -> None:
    plan = generate_webhook_delivery_reliability_plan(
        {
            "endpoints": [
                {"endpoint": "audit-events", "owner": "platform", "failure_rate": 0.2, "retry_policy": True},
                {"endpoint": "billing-events", "event_types": ["customer.invoice.created"], "failure_rate": "7%"},
            ]
        }
    )

    risky = plan["endpoint_rows"][0]
    assert plan["schema_version"] == "max-webhook-delivery-reliability-plan/v1"
    assert risky["id"] == "WDR-001"
    assert risky["endpoint"] == "billing-events"
    assert risky["risk"] == "high"
    assert set(risky["risk_factors"]) == {"high-failure-rate", "missing-retry-policy", "missing-owner", "customer-critical-event"}
    assert plan["summary"]["missing_retry_policy_count"] == 1
    assert plan["reliability_actions"][0]["endpoint_id"] == "WDR-001"


def test_webhook_delivery_reliability_markdown_sections_are_stable() -> None:
    payload = {"endpoints": [{"endpoint": "z", "failure_rate": 2}, {"endpoint": "a", "failure_rate": 2}]}

    first = render_webhook_delivery_reliability_plan_markdown(payload)
    second = render_webhook_delivery_reliability_plan_markdown(payload)

    assert first == second
    assert first.index("a") < first.index("z")
    for heading in ["## Endpoint Reliability", "## Retry Actions", "## Dead Letter Review", "## Policy"]:
        assert heading in first
