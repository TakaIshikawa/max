from __future__ import annotations

import json

from max.spec.capacity_forecast_plan import (
    CAPACITY_FORECAST_PLAN_SCHEMA_VERSION,
    KIND,
    generate_capacity_forecast_plan,
)


def _spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {"idea_id": "capacity-1", "domain": "launch"},
        "project": {
            "title": "Partner Launch Portal",
            "workflow_context": "partner onboarding launch",
            "target_users": "partner operations teams",
            "buyer": "alliances lead",
        },
        "solution": {
            "technical_approach": "FastAPI service with Postgres, Redis queue, and Salesforce integration.",
            "suggested_stack": {"api": "FastAPI", "database": "Postgres", "queue": "Redis"},
        },
        "execution": {"mvp_scope": ["partner intake", "status reporting"]},
        "metadata": {
            "capacity": {
                "expected_users": 250,
                "requests_per_day": 12000,
                "support_volume": 18,
                "data_volume": "50 GB of partner records",
            }
        },
        "evidence": {"signal_ids": ["sig-cap"], "source_idea_ids": ["idea-cap"]},
    }


def test_capacity_forecast_plan_reflects_metadata_hints() -> None:
    plan = generate_capacity_forecast_plan(_spec())

    assert plan["schema_version"] == CAPACITY_FORECAST_PLAN_SCHEMA_VERSION
    assert plan["kind"] == KIND
    assert plan["source"]["idea_id"] == "capacity-1"
    assert plan["summary"]["title"] == "Partner Launch Portal"
    assert plan["summary"]["forecast_posture"] == "scale_test_before_launch"
    assert plan["summary"]["expected_users"] == 250.0
    assert plan["summary"]["requests_per_day"] == 12000.0
    assert plan["summary"]["support_volume"] == 18.0
    assert plan["summary"]["data_volume"] == "50 GB of partner records"
    assert "250 expected users" in plan["demand_assumptions"][0]["description"]
    assert "12000 customer or system requests per day" in plan["demand_assumptions"][1]["description"]
    assert "18 launch support tickets per day" in plan["demand_assumptions"][2]["description"]
    assert "50 GB of partner records" in plan["capacity_drivers"][2]["description"]
    assert "12000 requests per day" in plan["resource_forecasts"][0]["forecast"]
    assert [item["id"] for item in plan["scaling_triggers"]] == ["ST1", "ST2", "ST3"]
    assert [item["id"] for item in plan["measurement_plan"]] == ["MP1", "MP2", "MP3", "MP4"]
    assert {item["role"] for item in plan["owner_roles"]} == {
        "product_owner",
        "technical_owner",
        "data_owner",
        "support_owner",
    }
    assert [item["reference"] for item in plan["evidence_references"]] == [
        "signal:sig-cap",
        "source_idea:idea-cap",
    ]
    assert json.loads(json.dumps(plan))["kind"] == KIND


def test_capacity_forecast_plan_sparse_input_defaults() -> None:
    plan = generate_capacity_forecast_plan({})

    assert plan["summary"]["title"] == "Untitled TactSpec"
    assert plan["summary"]["workflow_context"] == "primary workflow"
    assert plan["summary"]["target_user"] == "primary user"
    assert plan["summary"]["forecast_posture"] == "needs_capacity_discovery"
    assert plan["summary"]["expected_users"] is None
    assert plan["summary"]["requests_per_day"] is None
    assert plan["summary"]["support_volume"] is None
    assert plan["summary"]["data_volume"] is None
    assert "Unknown expected users" in plan["demand_assumptions"][0]["description"]
    assert "Unknown customer or system requests per day" in plan["demand_assumptions"][1]["description"]
    assert "Unknown launch data volume" in plan["resource_forecasts"][1]["forecast"]
    assert plan["evidence_references"] == []


def test_capacity_forecast_plan_is_deterministic() -> None:
    first = generate_capacity_forecast_plan(_spec())
    second = generate_capacity_forecast_plan(_spec())

    assert first == second
