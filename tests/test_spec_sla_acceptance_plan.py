from __future__ import annotations

from max.spec.sla_acceptance_plan import KIND, SCHEMA_VERSION, generate_sla_acceptance_plan


def test_sla_acceptance_plan_preserves_explicit_sla_inputs() -> None:
    plan = generate_sla_acceptance_plan(
        {
            "metadata": {
                "sla_acceptance": {
                    "targets": [{"name": "availability", "objective": "99.95%", "window": "calendar month", "owner": "sre"}],
                    "monitoring_signals": ["synthetic availability check"],
                    "dependencies": ["cloud load balancer"],
                }
            },
            "evidence": {"signal_ids": ["mon-1"]},
        }
    )

    assert plan["schema_version"] == SCHEMA_VERSION
    assert plan["kind"] == KIND
    assert plan["acceptance_targets"][0]["objective"] == "99.95%"
    assert plan["acceptance_targets"][0]["measurement_window"] == "calendar month"
    assert plan["measurement_plan"][0]["signal"] == "synthetic availability check"
    assert plan["approval_gates"][0]["status"] == "ready"


def test_sla_acceptance_plan_infers_defaults() -> None:
    plan = generate_sla_acceptance_plan({})

    assert plan["acceptance_targets"] == [
        {"id": "SLA1", "name": "availability", "objective": "99.9%", "measurement_window": "30 days", "owner": "service_owner"}
    ]
    assert plan["measurement_plan"][0]["signal"] == "monitoring signal pending setup"
    assert plan["approval_gates"][0]["status"] == "setup_required"
    assert plan["setup_actions"][0]["type"] == "monitoring_setup"


def test_sla_acceptance_plan_includes_breach_response_actions() -> None:
    plan = generate_sla_acceptance_plan(
        {
            "slas": [{"name": "p95 latency", "target": "< 300ms", "window": "7 days"}],
            "dependencies": ["cache"],
            "monitoring_signals": ["latency dashboard"],
        }
    )

    assert plan["escalation_rules"][0]["condition"] == "p95 latency misses < 300ms during 7 days"
    assert plan["breach_actions"][0]["dependency_review_required"] is True
    assert "remediate p95 latency below < 300ms" in plan["breach_actions"][0]["action"]
