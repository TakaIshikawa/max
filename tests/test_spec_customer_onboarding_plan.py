"""Tests for TactSpec customer onboarding plan generation."""

from __future__ import annotations

import json

import pytest

from max.spec import generate_customer_onboarding_plan as exported_generate
from max.spec import render_customer_onboarding_plan_markdown as exported_render
from max.spec.customer_onboarding_plan import (
    CUSTOMER_ONBOARDING_PLAN_SCHEMA_VERSION,
    generate_customer_onboarding_plan,
    render_customer_onboarding_plan_markdown,
)
from max.spec.generator import generate_spec_preview
from max.types.buildable_unit import BuildableCategory, BuildableUnit


def test_generate_customer_onboarding_plan_has_stable_schema_shape(
    sample_unit, sample_evaluation
) -> None:
    spec = generate_spec_preview(sample_unit, sample_evaluation)

    first = generate_customer_onboarding_plan(sample_unit, sample_evaluation, spec)
    second = generate_customer_onboarding_plan(sample_unit, sample_evaluation, spec)

    assert first == second
    assert first["schema_version"] == CUSTOMER_ONBOARDING_PLAN_SCHEMA_VERSION
    assert first["kind"] == "max.customer_onboarding_plan"
    assert first["idea_id"] == "bu-test001"
    assert first["source"]["tact_spec_schema_version"] == "tact-spec-preview/v1"
    assert first["idea"] == {
        "title": "MCP Test Framework",
        "one_liner": "Standardized testing for MCP servers",
        "target_user": "MCP server maintainer",
        "buyer": "developer platform lead",
        "workflow_context": "pre-release CI validation",
        "primary_scope": "A CLI tool that validates MCP server implementations",
        "current_workaround": "manual protocol testing",
        "first_10_customers": "teams publishing MCP servers",
        "validation_plan": "run against five open-source MCP servers",
        "value_proposition": "Reduce bugs in MCP servers by 80%",
        "recommendation": "yes",
        "overall_score": 78.0,
    }
    assert set(first) == {
        "schema_version",
        "kind",
        "idea_id",
        "source",
        "idea",
        "onboarding_segments",
        "first_session_checklist",
        "activation_milestones",
        "enablement_assets",
        "success_metrics",
        "handoff_risks",
        "evidence_references",
    }
    assert [segment["name"] for segment in first["onboarding_segments"]] == [
        "pilot_champion",
        "economic_sponsor",
        "first_customer_cohort",
        "fallback_or_workaround_owner",
    ]
    assert [item["id"] for item in first["first_session_checklist"]] == [
        "FS1",
        "FS2",
        "FS3",
        "FS4",
        "FS5",
    ]
    assert first["activation_milestones"][-1]["name"] == "risk_review_complete"
    assert first["enablement_assets"][0]["name"] == "first_session_script"
    assert first["success_metrics"][-1]["name"] == "risk_acceptance_coverage"
    assert first["handoff_risks"][0]["description"] == "protocol churn"
    assert "signal:sig-test001" in first["success_metrics"][0]["evidence_reference_ids"]


def test_generate_customer_onboarding_plan_is_json_serializable(sample_unit) -> None:
    plan = generate_customer_onboarding_plan(sample_unit)

    assert json.loads(json.dumps(plan))["idea_id"] == "bu-test001"


def test_generate_customer_onboarding_plan_degrades_for_sparse_inputs() -> None:
    sparse_unit = BuildableUnit(
        id="bu-sparse",
        title="Sparse Onboarding Helper",
        one_liner="Help customers start",
        category=BuildableCategory.AUTOMATION,
        problem="Customers need help",
        solution="",
        value_proposition="",
    )

    plan = generate_customer_onboarding_plan(sparse_unit)

    assert plan["source"]["evaluation_available"] is False
    assert plan["idea"]["target_user"] == "both"
    assert plan["idea"]["buyer"] == "customer sponsor"
    assert plan["idea"]["workflow_context"] == "Sparse Onboarding Helper workflow"
    assert plan["idea"]["primary_scope"] == "first usable Sparse Onboarding Helper workflow"
    assert [reference["id"] for reference in plan["evidence_references"]] == ["spec:fallback"]
    assert [risk["source"] for risk in plan["handoff_risks"]] == [
        "missing_evaluation",
        "missing_evidence",
    ]
    assert all(
        item["evidence_reference_ids"] == ["spec:fallback"]
        for section in (
            "onboarding_segments",
            "first_session_checklist",
            "activation_milestones",
            "enablement_assets",
            "success_metrics",
            "handoff_risks",
        )
        for item in plan[section]
    )


def test_render_customer_onboarding_plan_markdown_is_deterministic(
    sample_unit, sample_evaluation
) -> None:
    plan = generate_customer_onboarding_plan(sample_unit, sample_evaluation)

    first = render_customer_onboarding_plan_markdown(plan)
    second = render_customer_onboarding_plan_markdown(plan)

    assert first == second
    assert first.startswith("# MCP Test Framework Customer Onboarding Plan")
    assert f"- Schema version: {CUSTOMER_ONBOARDING_PLAN_SCHEMA_VERSION}" in first
    assert "## Onboarding Segments" in first
    assert "## First-Session Checklist" in first
    assert "## Activation Milestones" in first
    assert "## Enablement Assets" in first
    assert "## Success Metrics" in first
    assert "## Handoff Risks" in first
    assert "## Evidence References" in first
    assert "- Recommendation: yes" in first
    assert "- Overall score: 78.0" in first
    assert "run against five open-source MCP servers" in first
    assert "protocol churn" in first
    assert "`signal:sig-test001`" in first


def test_render_customer_onboarding_plan_markdown_rejects_unsupported_format(
    sample_unit,
) -> None:
    plan = generate_customer_onboarding_plan(sample_unit)

    with pytest.raises(
        ValueError, match="Unsupported customer onboarding plan render format: json"
    ):
        render_customer_onboarding_plan_markdown(plan, output_format="json")


def test_customer_onboarding_plan_is_importable_from_spec_package(
    sample_unit, sample_evaluation
) -> None:
    plan = exported_generate(sample_unit, sample_evaluation)
    markdown = exported_render(plan)

    assert plan["schema_version"] == CUSTOMER_ONBOARDING_PLAN_SCHEMA_VERSION
    assert markdown.startswith("# MCP Test Framework Customer Onboarding Plan")
