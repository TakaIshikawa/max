"""Tests for TactSpec post-launch monitoring plan generation."""

from __future__ import annotations

import csv
from io import StringIO
import json

import pytest

from max.spec import generate_post_launch_monitoring_plan as exported_generate
from max.spec import render_post_launch_monitoring_plan_csv as exported_render_csv
from max.spec import render_post_launch_monitoring_plan_markdown as exported_render
from max.spec.generator import generate_spec_preview
from max.spec.post_launch_monitoring_plan import (
    POST_LAUNCH_MONITORING_PLAN_CSV_COLUMNS,
    POST_LAUNCH_MONITORING_PLAN_SCHEMA_VERSION,
    generate_post_launch_monitoring_plan,
    render_post_launch_monitoring_plan_csv,
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


def test_render_post_launch_monitoring_plan_csv_has_generated_monitoring_rows(
    sample_unit, sample_evaluation
) -> None:
    plan = generate_post_launch_monitoring_plan(sample_unit, sample_evaluation)

    csv_text = render_post_launch_monitoring_plan_csv(plan)
    rows = list(csv.DictReader(StringIO(csv_text)))

    assert csv_text == render_post_launch_monitoring_plan_csv(plan)
    assert csv_text.splitlines()[0].split(",") == list(POST_LAUNCH_MONITORING_PLAN_CSV_COLUMNS)
    assert rows[0] == {
        "section": "health_metrics",
        "type": "metric",
        "idea_id": "bu-test001",
        "title": "MCP Test Framework",
        "item_id": "HM1",
        "phase": "production_candidate",
        "metric_or_signal": "workflow_success_rate",
        "threshold": ">= 95% during the first 7 launch days",
        "owner": "product_owner",
        "review_cadence": "",
        "escalation_path": "",
        "evidence": (
            "insight:ins-test001; signal:sig-test001; spec:evidence_rationale"
        ),
        "mitigation_action": "",
        "description": "Share of pre-release CI validation attempts completed successfully.",
        "measurement": "count(workflow_completed) / count(workflow_started)",
        "severity": "",
        "references": "summary.workflow_context; summary.validation_plan",
    }


def test_render_post_launch_monitoring_plan_csv_includes_all_monitoring_checks(
    sample_unit, sample_evaluation
) -> None:
    plan = generate_post_launch_monitoring_plan(sample_unit, sample_evaluation)

    rows = list(csv.DictReader(StringIO(render_post_launch_monitoring_plan_csv(plan))))

    assert [row["section"] for row in rows] == [
        *["health_metrics"] * 6,
        *["alert_thresholds"] * 6,
        *["review_cadence"] * 4,
        *["rollback_triggers"] * 4,
    ]
    assert [row["item_id"] for row in rows if row["section"] == "health_metrics"] == [
        "HM1",
        "HM2",
        "HM3",
        "HM4",
        "HM5",
        "HM6",
    ]
    assert rows[6]["item_id"] == "AT1"
    assert rows[6]["severity"] == "critical"
    assert rows[6]["escalation_path"].startswith("Pause rollout expansion")
    assert rows[-1]["item_id"] == "RT4"
    assert rows[-1]["mitigation_action"].startswith("Rollback the affected workflow")


def test_render_post_launch_monitoring_plan_csv_uses_csv_module_escaping() -> None:
    plan = {
        "idea_id": "idea-csv",
        "summary": {
            "title": 'Launch Room, "Alpha"\nPilot',
            "launch_posture": "limited_pilot",
        },
        "health_metrics": [
            {
                "id": "HM1",
                "name": "success, quoted",
                "description": 'Track "done", then report.',
                "measurement": "count(done)",
                "target": ">= 95%",
                "owner": "product_owner",
                "derived_from": ["summary.workflow_context"],
                "evidence_reference_ids": ["signal:sig-1"],
            }
        ],
        "alert_thresholds": [
            {
                "id": "AT1",
                "name": "drop",
                "severity": "critical",
                "threshold": 'Falls below "target",\nfor 30 minutes.',
                "response": 'Escalate to "owner", then pause.',
                "owner": "on_call_owner",
                "metric_ids": ["HM1"],
                "evidence_reference_ids": ["signal:sig-1"],
            }
        ],
    }

    csv_text = render_post_launch_monitoring_plan_csv(plan)
    rows = list(csv.DictReader(StringIO(csv_text)))

    assert '"Launch Room, ""Alpha""\nPilot"' in csv_text
    assert '"success, quoted"' in csv_text
    assert '"Falls below ""target"",\nfor 30 minutes."' in csv_text
    assert rows[0]["title"] == 'Launch Room, "Alpha"\nPilot'
    assert rows[1]["threshold"] == 'Falls below "target",\nfor 30 minutes.'


def test_render_post_launch_monitoring_plan_csv_handles_empty_sections() -> None:
    csv_text = render_post_launch_monitoring_plan_csv({"summary": {"title": "Empty Plan"}})
    rows = list(csv.DictReader(StringIO(csv_text)))

    assert csv_text == ",".join(POST_LAUNCH_MONITORING_PLAN_CSV_COLUMNS) + "\n"
    assert rows == []

    partial_text = render_post_launch_monitoring_plan_csv(
        {
            "idea_id": "idea-partial",
            "summary": {"title": "Partial Plan"},
            "review_cadence": [{"id": "RC1", "phase": "pilot", "cadence": "daily"}],
            "rollback_triggers": [{"id": "RT1", "name": "blocked", "action": "Pause."}],
        }
    )
    partial_rows = list(csv.DictReader(StringIO(partial_text)))

    assert [row["section"] for row in partial_rows] == [
        "review_cadence",
        "rollback_triggers",
    ]
    assert partial_rows[0]["phase"] == "pilot"
    assert partial_rows[0]["review_cadence"] == "daily"
    assert partial_rows[1]["mitigation_action"] == "Pause."


def test_post_launch_monitoring_plan_is_importable_from_spec_package(
    sample_unit, sample_evaluation
) -> None:
    plan = exported_generate(sample_unit, sample_evaluation)
    markdown = exported_render(plan)
    csv_text = exported_render_csv(plan)

    assert plan["schema_version"] == POST_LAUNCH_MONITORING_PLAN_SCHEMA_VERSION
    assert markdown.startswith("# MCP Test Framework Post-Launch Monitoring Plan")
    assert csv_text.startswith("section,type,idea_id,title")
