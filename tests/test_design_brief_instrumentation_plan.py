"""Tests for design brief instrumentation plan generation."""

from __future__ import annotations

import csv
import io
import json

import pytest

from max.analysis.design_brief_instrumentation_plan import (
    CSV_COLUMNS,
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
    assert any(
        alert["event_name"] == "guardrail_alert_triggered" for alert in plan["guardrail_alerts"]
    )
    assert any(alert["severity"] == "high" for alert in plan["guardrail_alerts"])
    assert any(
        "security approval" in alert["condition"].lower() for alert in plan["guardrail_alerts"]
    )


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
        "Hash or tokenize" in note for event in plan["events"] for note in event["privacy_notes"]
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


def test_render_design_brief_instrumentation_plan_csv_populated_rows_are_deterministic() -> None:
    plan = build_design_brief_instrumentation_plan(_brief())

    csv_text = render_design_brief_instrumentation_plan(plan, fmt="csv")
    repeated = render_design_brief_instrumentation_plan(plan, fmt="csv")
    rows = list(csv.DictReader(io.StringIO(csv_text)))

    assert csv_text == repeated
    assert csv_text.endswith("\n")
    assert csv_text.splitlines()[0] == ",".join(CSV_COLUMNS)
    assert len(rows) == (
        len(plan["events"])
        + len(plan["activation_funnel_steps"])
        + len(plan["retention_checkpoints"])
        + len(plan["guardrail_alerts"])
    )

    event_row = next(row for row in rows if row["name"] == "activation_started")
    assert event_row["design_brief_id"] == "dbf-instrument-001"
    assert event_row["item_type"] == "event"
    assert event_row["event_name"] == "activation_started"
    assert event_row["owner"] == "product analytics"
    assert event_row["priority"] == "high"
    assert event_row["trigger"] == "A qualified actor starts release governance review."
    assert (
        event_row["properties"]
        == "brief_id; account_id; actor_role; occurred_at; workflow_context; entry_point"
    )
    assert event_row["metric_linkage"] == "activation funnel"
    assert event_row["source_fields"] == "workflow_context; specific_user"
    assert "No raw user content or customer text." in event_row["privacy_notes"]
    assert (
        "Hash or tokenize actor and account identifiers before export."
        in event_row["privacy_notes"]
    )
    assert (
        "Store validation evidence references, not interview notes." in event_row["privacy_notes"]
    )

    assert any(
        row["section"] == "activation_funnel"
        and row["item_type"] == "metric"
        and row["event_name"] == "first_value_reached"
        for row in rows
    )
    alert_row = next(row for row in rows if row["section"] == "guardrail_alerts")
    assert alert_row["item_type"] == "alert"
    assert alert_row["owner"] == "risk owner"
    assert alert_row["priority"] == "high"
    assert alert_row["metric_linkage"] == "risk guardrail"
    assert "source_fields" in alert_row
    assert alert_row["source_fields"] == "risks"


def test_render_design_brief_instrumentation_plan_csv_serializes_nested_properties() -> None:
    plan = build_design_brief_instrumentation_plan(_brief())
    plan["events"][0]["required_properties"].append(
        {
            "rollout": {
                "stage": "pilot",
                "thresholds": ["warn", "block"],
            }
        }
    )
    plan["events"][0]["source_fields"].append({"evidence": ["signals", "insights"]})

    rows = list(
        csv.DictReader(io.StringIO(render_design_brief_instrumentation_plan(plan, fmt="csv")))
    )

    event_row = next(row for row in rows if row["name"] == "activation_started")
    assert "rollout: stage: pilot; thresholds: warn; block" in event_row["properties"]
    assert event_row["source_fields"] == (
        "workflow_context; specific_user; evidence: signals; insights"
    )


def test_render_design_brief_instrumentation_plan_csv_sparse_output_uses_fallback_rows() -> None:
    plan = build_design_brief_instrumentation_plan({"id": "dbf-sparse", "title": "Sparse Brief"})

    rows = list(
        csv.DictReader(io.StringIO(render_design_brief_instrumentation_plan(plan, fmt="csv")))
    )

    assert rows
    assert any(
        row["item_type"] == "event"
        and row["event_name"] == "mvp_scope_item_completed"
        and "primary MVP action" in row["trigger"]
        for row in rows
    )
    alert_row = next(row for row in rows if row["section"] == "guardrail_alerts")
    assert alert_row["name"] == "uncaptured_risk_discovered"
    assert alert_row["priority"] == "medium"
    assert alert_row["source_fields"] == "risks"


def test_render_design_brief_instrumentation_plan_markdown_json_and_invalid_format() -> None:
    plan = build_design_brief_instrumentation_plan(_brief())

    markdown = render_design_brief_instrumentation_plan(plan, fmt="markdown")
    json_text = render_design_brief_instrumentation_plan(plan, fmt="json")
    render_design_brief_instrumentation_plan(plan, fmt="csv")
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
    assert render_design_brief_instrumentation_plan(plan, fmt="markdown") == markdown

    parsed = json.loads(json_text)
    assert parsed["schema_version"] == SCHEMA_VERSION
    assert render_design_brief_instrumentation_plan(plan, fmt="json") == json_text

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
    assert (
        instrumentation_plan_filename({"id": "dbf-instrument-001"}, fmt="csv")
        == "dbf-instrument-001-instrumentation-plan.csv"
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
        "risks": [
            "Security approval may block rollout.",
            "Analytics gaps may hide failed reviews.",
        ],
        "first_10_customers": "platform teams shipping production agents",
        "evidence_counts": {"signals": 2, "insights": 1, "source_ideas": 2},
    }
    brief.update(overrides)
    return brief
