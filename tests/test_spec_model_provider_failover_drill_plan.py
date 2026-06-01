from __future__ import annotations

import json

from max.spec.model_provider_failover_drill_plan import generate_model_provider_failover_drill_plan


def test_model_provider_failover_drill_plan_surfaces_missing_fallback_blockers() -> None:
    plan = generate_model_provider_failover_drill_plan(
        [{"provider": "primary-a", "fallback_provider": "backup-a"}, {"provider": "primary-b"}],
        [{"name": "regional outage", "priority": 1}],
    )

    assert plan["summary"]["status"] == "blocked"
    assert plan["blockers"][0]["provider"] == "primary-b"
    assert plan["blockers"][0]["severity"] == "critical"


def test_model_provider_failover_drill_plan_sorts_scenarios_by_priority_then_name() -> None:
    plan = generate_model_provider_failover_drill_plan(
        [{"provider": "primary", "fallback": "backup"}],
        [
            {"name": "quota exhaustion", "priority": 2},
            {"name": "api outage", "priority": 1},
            {"name": "latency spike", "priority": 1},
        ],
    )

    assert [item["name"] for item in plan["scenarios"]] == [
        "api outage",
        "latency spike",
        "quota exhaustion",
    ]


def test_model_provider_failover_drill_plan_renders_rollback_window() -> None:
    plan = generate_model_provider_failover_drill_plan(
        [{"provider": "primary", "fallback": "backup"}],
        [{"name": "provider outage"}],
        rollback_window_minutes=45,
    )

    assert plan["summary"]["rollback_window_minutes"] == 45
    assert "within 45 minutes" in plan["rollback"][0]["description"]
    assert "fallback error rate exceeds threshold" in plan["rollback"][0]["criteria"]


def test_model_provider_failover_drill_plan_includes_validation_checks() -> None:
    plan = generate_model_provider_failover_drill_plan(
        [{"provider": "primary", "fallback": "backup"}],
        [{"name": "provider outage", "validation_probes": ["golden prompts", "latency SLO"]}],
    )

    assert [item["name"] for item in plan["validation"]] == [
        "provider outage: golden prompts",
        "provider outage: latency SLO",
    ]
    assert set(plan) >= {"prechecks", "execution", "validation", "rollback", "evidence"}
    assert json.loads(json.dumps(plan)) == plan
