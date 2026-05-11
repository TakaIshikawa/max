"""Tests for TactSpec chaos experiment plan generation."""

from __future__ import annotations

import json

from max.spec.chaos_experiment_plan import (
    CHAOS_EXPERIMENT_PLAN_SCHEMA_VERSION,
    generate_chaos_experiment_plan,
    render_chaos_experiment_plan_markdown,
)


def _rich_tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {"idea_id": "bu-chaos", "status": "approved", "domain": "platform"},
        "project": {
            "title": "Partner Webhook Router",
            "specific_user": "platform engineer",
            "buyer": "integration lead",
            "workflow_context": "partner webhook ingestion and delivery",
            "value_proposition": "prevents missed partner events",
        },
        "solution": {
            "technical_approach": "Python service with retries and dead-letter handling.",
            "suggested_stack": {
                "language": "python",
                "queue": "Kafka",
                "database": "Postgres",
                "alerts": "Slack",
            },
            "composability_notes": "Publishes delivery status to GitHub and Slack.",
        },
        "execution": {
            "mvp_scope": ["webhook intake", "delivery worker"],
            "validation_plan": "Replay signed webhook fixtures through the canary queue.",
            "risks": ["Partner API throttling can cause retry storms"],
            "acceptance_criteria": [
                {"criterion": "Webhook retries stop after delivery succeeds"},
                "Dead-letter events preserve source payload metadata",
            ],
        },
        "evaluation": {
            "overall_score": 78.0,
            "recommendation": "yes",
            "weaknesses": ["Unproven behavior during partner outage windows"],
        },
    }


def test_generate_chaos_experiment_plan_is_deterministic_and_structured() -> None:
    first = generate_chaos_experiment_plan(_rich_tact_spec())
    second = generate_chaos_experiment_plan(_rich_tact_spec())

    assert first == second
    assert first["schema_version"] == CHAOS_EXPERIMENT_PLAN_SCHEMA_VERSION
    assert first["kind"] == "max.chaos_experiment_plan"
    assert first["source"] == {
        "system": "max",
        "type": "tact_spec_preview",
        "idea_id": "bu-chaos",
        "status": "approved",
        "domain": "platform",
        "category": None,
        "tact_spec_schema_version": "tact-spec-preview/v1",
        "tact_spec_kind": "tact.project_spec",
    }
    assert set(first) == {
        "schema_version",
        "kind",
        "source",
        "summary",
        "scenarios",
        "guardrails",
        "telemetry_checks",
        "abort_conditions",
        "owner_roles",
        "recovery_validation",
    }
    assert first["summary"]["title"] == "Partner Webhook Router"
    assert first["summary"]["workflow_context"] == "partner webhook ingestion and delivery"
    assert first["summary"]["integration_count"] == 4
    assert first["summary"]["scenario_count"] == 4
    assert first["summary"]["risk_count"] == 1
    assert first["summary"]["acceptance_criteria_count"] == 2
    assert first["summary"]["evaluation_weakness_count"] == 1


def test_scenarios_derive_from_integrations_risks_criteria_and_weaknesses() -> None:
    plan = generate_chaos_experiment_plan(_rich_tact_spec())
    scenarios = {scenario["id"]: scenario for scenario in plan["scenarios"]}

    assert scenarios["CHAOS1"]["name"] == "dependency_degradation"
    assert "GitHub" in scenarios["CHAOS1"]["hypothesis"]
    assert "Partner API throttling" in scenarios["CHAOS2"]["hypothesis"]
    assert "Webhook retries stop after delivery succeeds" in scenarios["CHAOS3"]["hypothesis"]
    assert "Unproven behavior" in scenarios["CHAOS4"]["hypothesis"]
    assert scenarios["CHAOS1"]["blast_radius"] == (
        "One pilot cohort, synthetic account, or canary path for platform engineer."
    )
    assert scenarios["CHAOS1"]["guardrails"] == ["GR1", "GR2", "GR3"]
    assert scenarios["CHAOS1"]["abort_conditions"] == ["AB1", "AB2", "AB3"]
    assert scenarios["CHAOS1"]["telemetry_checks"] == ["TEL1", "TEL2", "TEL3"]
    assert scenarios["CHAOS1"]["recovery_validation"] == ["RV1", "RV2", "RV3"]
    assert scenarios["CHAOS1"]["owner_roles"] == [
        "experiment_owner",
        "service_owner",
        "on_call_owner",
    ]


def test_sparse_tact_spec_produces_useful_defaults() -> None:
    plan = generate_chaos_experiment_plan(
        {
            "schema_version": "tact-spec-preview/v1",
            "kind": "tact.project_spec",
            "source": {"idea_id": "bu-sparse"},
            "project": {"title": ""},
            "solution": {"suggested_stack": {}},
            "execution": {"risks": [], "mvp_scope": []},
            "evaluation": None,
        }
    )

    assert plan["summary"]["title"] == "bu-sparse"
    assert plan["summary"]["workflow_context"] == "primary workflow"
    assert plan["summary"]["target_user"] == "primary user"
    assert plan["summary"]["buyer"] == "launch sponsor"
    assert plan["summary"]["stack"] == "unspecified"
    assert plan["summary"]["integration_count"] == 1
    assert plan["scenarios"][0]["hypothesis"] == "Degrade primary dependency during primary workflow."
    assert plan["scenarios"][2]["hypothesis"] == (
        "Confirm recovery still satisfies acceptance criterion: "
        "Primary workflow completes with no unresolved user-visible error."
    )


def test_markdown_renderer_is_stable_and_includes_major_sections() -> None:
    plan = generate_chaos_experiment_plan(_rich_tact_spec())

    first = render_chaos_experiment_plan_markdown(plan)
    second = render_chaos_experiment_plan_markdown(plan)

    assert first == second
    assert first.startswith("# Partner Webhook Router Chaos Experiment Plan")
    assert f"- Schema version: {CHAOS_EXPERIMENT_PLAN_SCHEMA_VERSION}" in first
    assert "## Scenarios" in first
    assert "## Guardrails" in first
    assert "## Telemetry Checks" in first
    assert "## Abort Conditions" in first
    assert "## Owner Roles" in first
    assert "## Recovery Validation" in first
    assert "### CHAOS1: dependency_degradation" in first
    assert "- Blast radius: One pilot cohort" in first
    assert "`GR1`" in first
    assert "### TEL1: workflow_success_rate" in first
    assert "### RV2: replay_workflow" in first
    assert first.endswith("\n")


def test_plan_is_json_serializable() -> None:
    plan = generate_chaos_experiment_plan(_rich_tact_spec())

    assert json.loads(json.dumps(plan))["source"]["idea_id"] == "bu-chaos"
