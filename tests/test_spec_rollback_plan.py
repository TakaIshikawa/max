"""Tests for TactSpec rollback plan generation."""

from __future__ import annotations

from max.spec.generator import generate_spec_preview
from max.spec.rollback_plan import (
    ROLLBACK_PLAN_SCHEMA_VERSION,
    generate_rollback_plan,
    render_rollback_plan_markdown,
)


def test_generate_rollback_plan_includes_recovery_guidance(sample_unit, sample_evaluation) -> None:
    spec_preview = generate_spec_preview(sample_unit, sample_evaluation)

    plan = generate_rollback_plan(sample_unit, sample_evaluation, spec_preview)

    assert plan["schema_version"] == ROLLBACK_PLAN_SCHEMA_VERSION
    assert plan["kind"] == "max.rollback_plan"
    assert plan["idea_id"] == "bu-test001"
    assert plan["source"]["tact_spec_schema_version"] == "tact-spec-preview/v1"
    assert plan["summary"]["rollback_window"]
    assert {trigger["id"] for trigger in plan["rollback_triggers"]} >= {
        "trigger_validation_failure",
        "trigger_data_integrity",
        "trigger_operational_failure",
        "trigger_user_blocked",
        "trigger_domain_risk_1",
    }
    assert any(
        "reversible migration" in step["action"].lower()
        for step in plan["reversible_migration_steps"]
    )
    assert any(item["timing"] == "before_launch" for item in plan["data_backup_requirements"])
    assert any(signal["rollback_threshold"] for signal in plan["monitoring_signals"])
    assert {owner["role"] for owner in plan["owner_roles"]} >= {
        "product_owner",
        "release_owner",
        "technical_owner",
        "data_owner",
        "qa_owner",
    }
    assert all(item["status"] == "pending" for item in plan["go_no_go_checklist"])


def test_generate_rollback_plan_degrades_without_evaluation(sample_unit) -> None:
    plan = generate_rollback_plan(sample_unit, None)

    assert plan["source"]["evaluation_available"] is False
    assert plan["summary"]["recommendation"] is None
    assert "trigger_missing_evaluation" in {trigger["id"] for trigger in plan["rollback_triggers"]}
    assert any(
        item["task"] == "Utility evaluation is present or explicitly waived."
        for item in plan["go_no_go_checklist"]
    )


def test_render_rollback_plan_markdown_is_deterministic(sample_unit, sample_evaluation) -> None:
    plan = generate_rollback_plan(sample_unit, sample_evaluation)

    first = render_rollback_plan_markdown(plan)
    second = render_rollback_plan_markdown(plan)

    assert first == second
    assert first.startswith("# MCP Test Framework Rollback Plan")
    assert "## Rollback Triggers" in first
    assert "## Reversible Migration Steps" in first
    assert "## Data Backup Requirements" in first
    assert "## Monitoring Signals" in first
    assert "## Owner Roles" in first
    assert "## Go/No-Go Checklist" in first
    assert "trigger_domain_risk_1" in first
    assert "protocol churn" in first
