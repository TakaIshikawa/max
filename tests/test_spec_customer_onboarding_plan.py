"""Tests for TactSpec customer onboarding plan generation."""

from __future__ import annotations

import csv
import json
from io import StringIO

import pytest

from max.spec import generate_customer_onboarding_plan as exported_generate
from max.spec import render_customer_onboarding_plan_csv as exported_render_csv
from max.spec import render_customer_onboarding_plan_markdown as exported_render
from max.spec.customer_onboarding_plan import (
    CUSTOMER_ONBOARDING_PLAN_CSV_COLUMNS,
    CUSTOMER_ONBOARDING_PLAN_SCHEMA_VERSION,
    generate_customer_onboarding_plan,
    render_customer_onboarding_plan_csv,
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


def test_render_customer_onboarding_plan_csv_has_stable_headers_and_sections(
    sample_unit, sample_evaluation
) -> None:
    plan = generate_customer_onboarding_plan(sample_unit, sample_evaluation)

    first = render_customer_onboarding_plan_csv(plan)
    second = render_customer_onboarding_plan_csv(plan)
    reader = csv.DictReader(StringIO(first))
    rows = list(reader)

    assert first == second
    assert first.endswith("\n")
    assert reader.fieldnames == list(CUSTOMER_ONBOARDING_PLAN_CSV_COLUMNS)
    assert {row["section"] for row in rows} == {
        "onboarding_segments",
        "first_session_checklist",
        "activation_milestones",
        "enablement_assets",
        "success_metrics",
        "handoff_risks",
    }
    assert all(row["idea_id"] == "bu-test001" for row in rows)
    assert all(row["title"] == "MCP Test Framework" for row in rows)


def test_render_customer_onboarding_plan_csv_includes_representative_rows(
    sample_unit, sample_evaluation
) -> None:
    plan = generate_customer_onboarding_plan(sample_unit, sample_evaluation)

    rows = list(csv.DictReader(StringIO(render_customer_onboarding_plan_csv(plan))))

    phase = next(row for row in rows if row["row_id"] == "SEG1")
    assert phase["row_type"] == "phase"
    assert phase["name"] == "pilot_champion"
    assert phase["phase"] == "high_touch"
    assert phase["owner"] == "MCP server maintainer"
    assert "run against five open-source MCP servers" in phase["success_criteria"]

    task = next(row for row in rows if row["row_id"] == "FS2")
    assert task["section"] == "first_session_checklist"
    assert task["row_type"] == "task"
    assert task["owner"] == "technical_owner"
    assert task["timing"] == "first_session"
    assert task["status"] == "pending"
    assert "A CLI tool that validates MCP server implementations" in task["success_criteria"]

    metric = next(row for row in rows if row["row_id"] == "SM1")
    assert metric["row_type"] == "success_metric"
    assert metric["phase"] == "activation"
    assert metric["owner"] == "customer_success_owner"
    assert metric["metric"] == ("count(first_sessions_completed) / count(first_sessions_started)")
    assert "signal:sig-test001" in metric["evidence_references"]

    risk = next(row for row in rows if row["row_id"] == "HR1")
    assert risk["row_type"] == "risk"
    assert risk["phase"] == "handoff"
    assert risk["status"] == "elevated"
    assert risk["risk"] == "protocol churn"


def test_render_customer_onboarding_plan_csv_flattens_multiple_milestones_and_tasks() -> None:
    plan = {
        "schema_version": CUSTOMER_ONBOARDING_PLAN_SCHEMA_VERSION,
        "kind": "max.customer_onboarding_plan",
        "idea_id": "bu-onboard",
        "idea": {"title": "Customer Launch"},
        "milestones": [
            {
                "id": "M1",
                "name": "Kickoff ready",
                "owner": "customer_success",
                "target_timing": "week 0",
                "description": "Customer is prepared for setup.",
                "success_criteria": "Sponsor, users, and sample data are confirmed.",
                "prerequisites": ["signed order", "admin access"],
                "customer_facing_artifacts": ["kickoff deck"],
                "tasks": [
                    {
                        "id": "T1",
                        "task": "Confirm sponsor",
                        "owner": "customer_success",
                        "timing": "before kickoff",
                        "success_criteria": "Sponsor accepts first-value target.",
                    },
                    {
                        "id": "T2",
                        "task": "Provision sandbox",
                        "owner": "technical_owner",
                        "timing": "before kickoff",
                        "prerequisites": ["admin access"],
                    },
                ],
            },
            {
                "id": "M2",
                "name": "First value",
                "owner": "product_owner",
                "target_window": "week 1",
                "exit_criteria": "Customer completes a qualified workflow.",
            },
        ],
        "tasks": [
            {
                "id": "T3",
                "name": "Schedule handoff",
                "owner": "launch_owner",
                "due": "week 2",
                "done_when": "Ongoing owner accepts next steps.",
            }
        ],
        "success_criteria": [
            {
                "id": "SC1",
                "metric": "activation_rate",
                "target": ">= 80%",
                "owner": "customer_success",
            }
        ],
        "customer_facing_artifacts": [
            {
                "id": "CA1",
                "name": "Setup guide",
                "owner": "technical_owner",
                "ready_when": "Reviewed by support.",
            }
        ],
        "risks": [
            {
                "id": "R1",
                "risk": "Customer data access may delay setup.",
                "mitigation": "Prepare sample data fallback.",
                "owner": "product_owner",
            }
        ],
    }

    rows = list(csv.DictReader(StringIO(render_customer_onboarding_plan_csv(plan))))

    assert [row["row_id"] for row in rows] == [
        "M1",
        "M1.T1",
        "M1.T2",
        "M2",
        "T3",
        "SC1",
        "CA1",
        "R1",
    ]
    assert rows[0]["row_type"] == "milestone"
    assert rows[0]["owner"] == "customer_success"
    assert rows[0]["timing"] == "week 0"
    assert rows[0]["success_criteria"] == "Sponsor, users, and sample data are confirmed."
    assert rows[0]["details"] == (
        "customer_facing_artifacts=kickoff deck; prerequisites=signed order | admin access"
    )
    assert rows[2]["row_type"] == "task"
    assert rows[2]["details"] == "parent_milestone=Kickoff ready; prerequisites=admin access"
    assert rows[4]["section"] == "onboarding_tasks"
    assert rows[4]["timing"] == "week 2"
    assert rows[5]["metric"] == "activation_rate"
    assert rows[6]["section"] == "customer_facing_artifacts"
    assert rows[7]["risk"] == "Customer data access may delay setup."
    assert rows[7]["success_criteria"] == "Prepare sample data fallback."


def test_render_customer_onboarding_plan_csv_escapes_commas_quotes_and_newlines() -> None:
    plan = {
        "schema_version": CUSTOMER_ONBOARDING_PLAN_SCHEMA_VERSION,
        "kind": "max.customer_onboarding_plan",
        "idea_id": "bu-escape",
        "idea": {"title": "Launch, Onboarding"},
        "tasks": [
            {
                "id": "T1",
                "name": 'Send "welcome", guide',
                "description": "Line one\nLine two, with comma",
                "owner": "customer_success",
            }
        ],
    }

    csv_text = render_customer_onboarding_plan_csv(plan)
    row = next(csv.DictReader(StringIO(csv_text)))

    assert '"Launch, Onboarding"' in csv_text
    assert row["name"] == 'Send "welcome", guide'
    assert row["description"] == "Line one Line two, with comma"


def test_render_customer_onboarding_plan_csv_handles_minimal_plan_dictionaries() -> None:
    csv_text = render_customer_onboarding_plan_csv(
        {
            "schema_version": CUSTOMER_ONBOARDING_PLAN_SCHEMA_VERSION,
            "kind": "max.customer_onboarding_plan",
            "tasks": [{"task": "Confirm kickoff"}],
            "risks": [{"risk": "Sponsor unavailable"}],
        }
    )
    rows = list(csv.DictReader(StringIO(csv_text)))

    assert [row["row_id"] for row in rows] == ["T1", "R1"]
    assert rows[0]["name"] == "Confirm kickoff"
    assert rows[0]["owner"] == ""
    assert rows[0]["timing"] == ""
    assert rows[1]["risk"] == "Sponsor unavailable"


def test_customer_onboarding_plan_is_importable_from_spec_package(
    sample_unit, sample_evaluation
) -> None:
    plan = exported_generate(sample_unit, sample_evaluation)
    markdown = exported_render(plan)
    csv_text = exported_render_csv(plan)

    assert plan["schema_version"] == CUSTOMER_ONBOARDING_PLAN_SCHEMA_VERSION
    assert markdown.startswith("# MCP Test Framework Customer Onboarding Plan")
    assert list(csv.DictReader(StringIO(csv_text)).fieldnames or []) == list(
        CUSTOMER_ONBOARDING_PLAN_CSV_COLUMNS
    )
