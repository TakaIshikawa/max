from __future__ import annotations

import json

from max.spec.slo_burn_rate_response_plan import (
    SCHEMA_VERSION,
    generate_slo_burn_rate_response_plan,
    render_slo_burn_rate_response_plan_markdown,
)


def _spec() -> dict:
    return {
        "project": {"title": "Checkout Reliability"},
        "service": {"name": "checkout-api", "owner": "Payments SRE"},
        "slo_targets": [{"name": "availability", "target": "99.95%", "indicator": "successful_requests"}],
        "burn_rate_windows": [
            {"window": "6h", "burn_rate": 1.4, "exhaustion_eta": "36 hours"},
            {"window": "1h", "burn_rate": 2.8, "exhaustion_eta": "8 hours"},
            {"window": "30d", "burn_rate": 0.4},
        ],
        "alert_thresholds": [
            {"name": "slow_burn", "window": "6h", "burn_rate": 1.2, "owner": "SRE"},
            {"name": "fast_burn", "window": "1h", "burn_rate": 2.0, "owner": "SRE"},
        ],
        "owners": {"incident_commander": "Mina", "customer_comms": "Tara"},
        "escalation_actions": [
            {"name": "customer_update", "severity": "warning", "owner": "customer_comms", "timing": "30 minutes", "action": "Post impacted-account update."},
            {"name": "rollback_review", "severity": "critical", "owner": "incident_commander", "timing": "10 minutes", "action": "Decide rollback or traffic shed."},
        ],
        "customer_impact_notes": ["Checkout attempts may fail for premium merchants."],
        "evidence": {"signal_ids": ["burn-1"], "rationale": "SLO dashboard shows elevated 5xx."},
    }


def test_burn_rate_plan_returns_stable_structured_output() -> None:
    first = generate_slo_burn_rate_response_plan(_spec())
    second = generate_slo_burn_rate_response_plan(_spec())

    assert first == second
    assert first["schema_version"] == SCHEMA_VERSION
    assert first["kind"] == "max.slo_burn_rate_response_plan"
    assert json.loads(json.dumps(first))["summary"]["service"] == "checkout-api"
    assert first["summary"]["classification"] == "critical"
    assert [row["classification"] for row in first["burn_rate_windows"]] == ["critical", "warning", "healthy"]
    assert [row["severity"] for row in first["alert_thresholds"]] == ["critical", "warning"]
    assert [row["name"] for row in first["response_actions"]] == ["rollback_review", "customer_update"]
    assert first["owners"][0] == {"role": "customer_comms", "owner": "Tara"}
    assert [row["reference"] for row in first["evidence"]] == ["signal:burn-1", "SLO dashboard shows elevated 5xx."]


def test_burn_rate_classifies_healthy_and_warning_inputs() -> None:
    healthy = generate_slo_burn_rate_response_plan({"burn_rate_windows": [{"window": "30d", "burn_rate": 0.8}]})
    warning = generate_slo_burn_rate_response_plan({"burn_rate_windows": [{"window": "6h", "burn_rate": 1.5}]})

    assert healthy["summary"]["classification"] == "healthy"
    assert healthy["burn_rate_windows"][0]["classification"] == "healthy"
    assert warning["summary"]["classification"] == "warning"
    assert warning["burn_rate_windows"][0]["classification"] == "warning"


def test_burn_rate_markdown_is_stable_and_contains_operational_sections() -> None:
    plan = generate_slo_burn_rate_response_plan(_spec())

    first = render_slo_burn_rate_response_plan_markdown(plan)
    second = render_slo_burn_rate_response_plan_markdown(plan)

    assert first == second
    assert first.startswith("# Checkout Reliability SLO Burn-Rate Response Plan")
    assert f"- Schema version: {SCHEMA_VERSION}" in first
    assert "## Burn-Rate Windows" in first
    assert "### BRW2: 1h" in first
    assert "## Escalation Steps" in first
    assert "Decide rollback or traffic shed." in first
    assert "## Customer Impact" in first
    assert "Checkout attempts may fail for premium merchants." in first
