"""Tests for TactSpec post-launch monitoring plan generation."""

from __future__ import annotations

import json

import pytest

from max.spec import generate_post_launch_monitoring_plan as exported_generate
from max.spec import render_post_launch_monitoring_plan_markdown as exported_render
from max.spec.generator import generate_spec_preview
from max.spec.post_launch_monitoring_plan import (
    POST_LAUNCH_MONITORING_PLAN_SCHEMA_VERSION,
    generate_post_launch_monitoring_plan,
    render_post_launch_monitoring_plan_markdown,
)
from max.types.buildable_unit import BuildableCategory, BuildableUnit


def test_generate_post_launch_monitoring_plan_has_stable_schema_shape(
    sample_unit, sample_evaluation
) -> None:
    spec = generate_spec_preview(sample_unit, sample_evaluation)

    first = generate_post_launch_monitoring_plan(sample_unit, sample_evaluation, spec)
    second = generate_post_launch_monitoring_plan(sample_unit, sample_evaluation, spec)

    assert first == second
    assert first["schema_version"] == POST_LAUNCH_MONITORING_PLAN_SCHEMA_VERSION
    assert first["kind"] == "max.post_launch_monitoring_plan"
    assert first["idea_id"] == "bu-test001"
    assert first["source"]["tact_spec_schema_version"] == "tact-spec-preview/v1"
    assert first["summary"] == {
        "title": "MCP Test Framework",
        "one_liner": "Standardized testing for MCP servers",
        "target_user": "MCP server maintainer",
        "buyer": "developer platform lead",
        "workflow_context": "pre-release CI validation",
        "primary_scope": "A CLI tool that validates MCP server implementations",
        "validation_plan": "run against five open-source MCP servers",
        "launch_posture": "production_candidate",
        "recommendation": "yes",
        "overall_score": 78.0,
    }
    assert set(first) == {
        "schema_version",
        "kind",
        "idea_id",
        "source",
        "summary",
        "health_metrics",
        "alert_thresholds",
        "review_cadence",
        "rollback_triggers",
        "owners",
        "evidence_references",
    }
    assert [item["name"] for item in first["health_metrics"]] == [
        "workflow_success_rate",
        "workflow_latency_p95",
        "workflow_error_rate",
        "qualified_activation_count",
        "support_blocker_count",
        "known_risk_indicator_count",
    ]
    assert first["health_metrics"][1]["target"] == "p95 <= 1500 ms"
    assert any(alert["name"] == "known_risk_materialized" for alert in first["alert_thresholds"])
    assert any(trigger["name"] == "known_risk_unmitigated" for trigger in first["rollback_triggers"])
    assert first["review_cadence"][0]["phase"] == "first_24_hours"
    assert first["owners"][0]["suggested_owner"] == "developer platform lead"
    assert "signal:sig-test001" in first["health_metrics"][0]["evidence_reference_ids"]


def test_generate_post_launch_monitoring_plan_is_json_serializable(sample_unit) -> None:
    plan = generate_post_launch_monitoring_plan(sample_unit)

    assert json.loads(json.dumps(plan))["idea_id"] == "bu-test001"


def test_generate_post_launch_monitoring_plan_degrades_for_sparse_inputs() -> None:
    sparse_unit = BuildableUnit(
        id="bu-sparse",
        title="Sparse Agent Helper",
        one_liner="Help agents do a task",
        category=BuildableCategory.AUTOMATION,
        problem="Agents need help",
        solution="",
        value_proposition="",
    )

    plan = generate_post_launch_monitoring_plan(sparse_unit)

    assert plan["source"]["evaluation_available"] is False
    assert plan["summary"]["target_user"] == "both"
    assert plan["summary"]["buyer"] == "launch sponsor"
    assert plan["summary"]["workflow_context"] == "Sparse Agent Helper workflow"
    assert plan["summary"]["launch_posture"] == "limited_pilot"
    assert plan["health_metrics"][0]["target"] == ">= 95% during the first 7 launch days"
    assert [reference["id"] for reference in plan["evidence_references"]] == ["spec:fallback"]
    assert [trigger["id"] for trigger in plan["rollback_triggers"]] == ["RT1", "RT2", "RT3"]
    assert {owner["role"] for owner in plan["owners"]} == {
        "launch_owner",
        "product_owner",
        "technical_owner",
        "on_call_owner",
        "support_owner",
    }


def test_render_post_launch_monitoring_plan_markdown_is_deterministic(
    sample_unit, sample_evaluation
) -> None:
    plan = generate_post_launch_monitoring_plan(sample_unit, sample_evaluation)

    first = render_post_launch_monitoring_plan_markdown(plan)
    second = render_post_launch_monitoring_plan_markdown(plan)

    assert first == second
    assert first.startswith("# MCP Test Framework Post-Launch Monitoring Plan")
    assert f"- Schema version: {POST_LAUNCH_MONITORING_PLAN_SCHEMA_VERSION}" in first
    assert "## Health Metrics" in first
    assert "## Alert Thresholds" in first
    assert "## Review Cadence" in first
    assert "## Rollback Triggers" in first
    assert "## Owners" in first
    assert "## Evidence References" in first
    assert "### HM1: workflow_success_rate" in first
    assert "### AT1: success_rate_drop (critical)" in first
    assert "protocol churn" in first
    assert "`signal:sig-test001`" in first


def test_render_post_launch_monitoring_plan_markdown_rejects_unsupported_format(
    sample_unit,
) -> None:
    plan = generate_post_launch_monitoring_plan(sample_unit)

    with pytest.raises(
        ValueError, match="Unsupported post-launch monitoring plan render format: json"
    ):
        render_post_launch_monitoring_plan_markdown(plan, output_format="json")


def test_post_launch_monitoring_plan_is_importable_from_spec_package(
    sample_unit, sample_evaluation
) -> None:
    plan = exported_generate(sample_unit, sample_evaluation)
    markdown = exported_render(plan)

    assert plan["schema_version"] == POST_LAUNCH_MONITORING_PLAN_SCHEMA_VERSION
    assert markdown.startswith("# MCP Test Framework Post-Launch Monitoring Plan")
