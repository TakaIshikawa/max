from __future__ import annotations

import json

from max.spec.maintenance_window_plan import (
    KIND,
    MAINTENANCE_WINDOW_PLAN_SCHEMA_VERSION,
    generate_maintenance_window_plan,
)


def _spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {"idea_id": "maint-1", "domain": "operations"},
        "project": {
            "title": "Billing Migration",
            "workflow_context": "invoice payment workflow",
            "specific_user": "billing operator",
            "buyer": "finance director",
        },
        "execution": {
            "mvp_scope": ["billing database", "payment worker"],
            "risks": ["Customer-impacting downtime during payment migration."],
        },
        "metadata": {
            "maintenance": {
                "window": "Sunday 02:00-03:00 UTC",
                "duration": "45 minutes",
                "timezone": "UTC",
                "customer_impacting": True,
                "downtime_expected": True,
                "impacted_users": ["billing operators", "customers paying invoices"],
                "systems": ["billing API", "payment queue"],
            }
        },
        "evidence": {
            "insight_ids": ["ins-1"],
            "signal_ids": ["sig-1"],
            "rationale": "Payment migration requires a planned outage.",
        },
    }


def test_maintenance_window_plan_complete_shape_and_strict_cadence() -> None:
    plan = generate_maintenance_window_plan(_spec())

    assert plan["schema_version"] == MAINTENANCE_WINDOW_PLAN_SCHEMA_VERSION
    assert plan["kind"] == KIND
    assert plan["source"]["idea_id"] == "maint-1"
    assert plan["summary"]["title"] == "Billing Migration"
    assert plan["summary"]["maintenance_strictness"] == "strict"
    assert plan["summary"]["communication_cadence"] == "high-touch"
    assert plan["window_strategy"]["window"] == "Sunday 02:00-03:00 UTC"
    assert plan["window_strategy"]["customer_impact"] == "customer-visible downtime expected"
    assert set(plan) == {
        "schema_version",
        "kind",
        "source",
        "summary",
        "window_strategy",
        "impacted_users",
        "communication_timeline",
        "pre_checks",
        "execution_steps",
        "rollback_or_abort_criteria",
        "post_checks",
        "owner_roles",
        "evidence_references",
    }

    assert [item["segment"] for item in plan["impacted_users"]] == [
        "billing operators",
        "customers paying invoices",
    ]
    assert [item["milestone"] for item in plan["communication_timeline"]] == [
        "T-14 days",
        "T-3 days",
        "T-1 hour",
        "T+30 minutes",
    ]
    assert [item["id"] for item in plan["pre_checks"]] == ["PC1", "PC2", "PC3", "PC4"]
    assert [item["id"] for item in plan["execution_steps"]] == ["ES1", "ES2", "ES3", "ES4"]
    assert any(item["action"] == "rollback immediately" for item in plan["rollback_or_abort_criteria"])
    assert [item["id"] for item in plan["post_checks"]] == ["PO1", "PO2", "PO3"]
    assert {item["role"] for item in plan["owner_roles"]} == {
        "release_owner",
        "technical_owner",
        "communications_owner",
        "support_owner",
    }
    assert [item["reference"] for item in plan["evidence_references"]] == [
        "insight:ins-1",
        "signal:sig-1",
        "Payment migration requires a planned outage.",
    ]
    assert json.loads(json.dumps(plan))["kind"] == KIND


def test_maintenance_window_plan_sparse_input_defaults() -> None:
    plan = generate_maintenance_window_plan({})

    assert plan["summary"]["title"] == "Untitled TactSpec"
    assert plan["summary"]["workflow_context"] == "primary workflow"
    assert plan["summary"]["maintenance_strictness"] == "standard"
    assert plan["summary"]["communication_cadence"] == "standard"
    assert plan["window_strategy"]["window"] == "lowest-usage staffed window"
    assert plan["impacted_users"][0]["segment"] == "primary user"
    assert [item["milestone"] for item in plan["communication_timeline"]] == [
        "T-7 days",
        "T-1 hour",
        "T+30 minutes",
    ]
    assert plan["evidence_references"] == []


def test_maintenance_window_plan_is_deterministic() -> None:
    first = generate_maintenance_window_plan(_spec())
    second = generate_maintenance_window_plan(_spec())

    assert first == second
