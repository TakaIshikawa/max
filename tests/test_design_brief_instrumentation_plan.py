"""Tests for design brief instrumentation plan generation."""

from __future__ import annotations

import json

import pytest

from max.analysis.design_brief_instrumentation_plan import (
    SCHEMA_VERSION,
    build_design_brief_instrumentation_plan,
    instrumentation_plan_filename,
    render_design_brief_instrumentation_plan,
    write_design_brief_instrumentation_plan,
)


def test_build_design_brief_instrumentation_plan_derives_required_event_categories() -> None:
    first = build_design_brief_instrumentation_plan(_brief())
    second = build_design_brief_instrumentation_plan(_brief())

    assert first == second
    assert first["schema_version"] == SCHEMA_VERSION
    assert first["kind"] == "max.design_brief.instrumentation_plan"
    assert first["design_brief"]["id"] == "dbf-instrument-001"
    assert first["summary"]["activation_event_count"] >= 1
    assert first["summary"]["value_event_count"] >= 1
    assert first["summary"]["retention_event_count"] >= 1
    assert first["summary"]["guardrail_event_count"] >= 1
    assert first["summary"]["missing_input_count"] == 0

    event_names = {event["name"] for event in first["events"]}
    assert {
        "activation_started",
        "first_value_reached",
        "core_workflow_repeated",
        "guardrail_alert_triggered",
    } <= event_names
    assert any("release governance review" in event["trigger"] for event in first["events"])
    assert any("JSON instrumentation plan" in event["trigger"] for event in first["events"])
    assert all(event["required_properties"] for event in first["events"])
    assert all(event["privacy_notes"] for event in first["events"])
    assert json.loads(json.dumps(first))["schema_version"] == SCHEMA_VERSION


def test_build_design_brief_instrumentation_plan_includes_funnels_checkpoints_and_alerts() -> None:
    plan = build_design_brief_instrumentation_plan(_brief())

    assert [step["event_name"] for step in plan["activation_funnel_steps"]] == [
        "activation_started",
        "mvp_scope_item_completed",
        "first_value_reached",
    ]
    assert any(
        checkpoint["event_name"] == "retention_checkpoint_met"
        for checkpoint in plan["retention_checkpoints"]
    )
    assert any(alert["event_name"] == "guardrail_alert_triggered" for alert in plan["guardrail_alerts"])
    assert any(alert["severity"] == "high" for alert in plan["guardrail_alerts"])
    assert any("security approval" in alert["condition"].lower() for alert in plan["guardrail_alerts"])


def test_privacy_sensitive_terms_create_explicit_privacy_notes() -> None:
    plan = build_design_brief_instrumentation_plan(
        _brief(
            workflow_context="security review with customer PII and approval history",
            risks=["Slack messages may include credentials", "SOC2 audit trail is regulated"],
        )
    )

    assert plan["summary"]["privacy_note_count"] >= 3
    assert any("Privacy-sensitive terms detected" in note for note in plan["privacy_notes"])
    assert any("pii" in note.lower() for note in plan["privacy_notes"])
    assert any(
        "Hash or tokenize" in note
        for event in plan["events"]
        for note in event["privacy_notes"]
    )


def test_sparse_design_brief_reports_missing_inputs_and_fallbacks() -> None:
    plan = build_design_brief_instrumentation_plan(
        {
            "id": "dbf-sparse",
            "title": "Sparse Brief",
        }
    )

    missing_fields = [item["field"] for item in plan["missing_inputs"]]
    assert missing_fields == [
        "workflow_context",
        "mvp_scope",
        "success_metric",
        "validation_plan",
        "risks",
    ]
    assert plan["summary"]["missing_input_count"] == 5
    assert any(
        event["name"] == "guardrail_alert_triggered" and event["category"] == "guardrail"
        for event in plan["events"]
    )
    assert plan["guardrail_alerts"][0]["name"] == "uncaptured_risk_discovered"
    assert any("primary MVP action" in event["trigger"] for event in plan["events"])


def test_render_design_brief_instrumentation_plan_markdown_json_and_invalid_format() -> None:
    plan = build_design_brief_instrumentation_plan(_brief())

    markdown = render_design_brief_instrumentation_plan(plan, fmt="markdown")
    assert markdown.startswith("# Instrumentation Plan: Instrumentation Plan Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert "Design brief: `dbf-instrument-001`" in markdown
    assert "## Events" in markdown
    assert "| Event | Category | Trigger | Required Properties | Privacy Notes |" in markdown
    assert "`activation_started`" in markdown
    assert "`first_value_reached`" in markdown
    assert "## Activation Funnel" in markdown
    assert "## Retention Checkpoints" in markdown
    assert "## Guardrail Alerts" in markdown
    assert "## Privacy Notes" in markdown
    assert "## Missing Inputs" in markdown
    assert "- None" in markdown

    parsed = json.loads(render_design_brief_instrumentation_plan(plan, fmt="json"))
    assert parsed["schema_version"] == SCHEMA_VERSION

    with pytest.raises(ValueError, match="Unsupported instrumentation plan format: yaml"):
        render_design_brief_instrumentation_plan(plan, fmt="yaml")


def test_write_design_brief_instrumentation_plan_and_filename(tmp_path) -> None:
    plan = build_design_brief_instrumentation_plan(_brief())
    path = tmp_path / instrumentation_plan_filename(_brief(), fmt="markdown")

    write_design_brief_instrumentation_plan(path, plan)

    assert path.name == "dbf-instrument-001-instrumentation-plan.md"
    assert path.read_text(encoding="utf-8").startswith(
        "# Instrumentation Plan: Instrumentation Plan Brief"
    )
    assert (
        instrumentation_plan_filename({"id": "dbf-instrument-001"}, fmt="json")
        == "dbf-instrument-001-instrumentation-plan.json"
    )


def _brief(**overrides: object) -> dict[str, object]:
    brief: dict[str, object] = {
        "id": "dbf-instrument-001",
        "title": "Instrumentation Plan Brief",
        "domain": "developer-tools",
        "theme": "agent-release-governance",
        "lead_idea_id": "bu-instrument-lead",
        "source_idea_ids": ["bu-instrument-lead", "bu-instrument-support"],
        "readiness_score": 86.0,
        "design_status": "approved",
        "specific_user": "platform engineer",
        "buyer": "VP of Engineering",
        "workflow_context": "release governance review",
        "problem": "Platform teams cannot see which releases need governance review.",
        "merged_product_concept": "A release governance brief with implementation-ready analytics.",
        "value_proposition": "Reduce approval delays and make release risk explicit.",
        "mvp_scope": ["JSON instrumentation plan", "Markdown instrumentation plan"],
        "validation_plan": "Interview platform engineers and engineering buyers before implementation.",
        "success_metric": "4 of 6 interviewees confirm the release governance workflow is urgent.",
        "risks": ["Security approval may block rollout.", "Analytics gaps may hide failed reviews."],
        "first_10_customers": "platform teams shipping production agents",
        "evidence_counts": {"signals": 2, "insights": 1, "source_ideas": 2},
    }
    brief.update(overrides)
    return brief
