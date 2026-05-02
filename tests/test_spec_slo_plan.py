"""Tests for TactSpec SLO plan generation."""

from __future__ import annotations

import csv
import io
import json

import pytest

from max.spec import generate_slo_plan as exported_generate
from max.spec import render_slo_plan_csv as exported_render_csv
from max.spec import render_slo_plan_markdown as exported_render
from max.spec.generator import generate_spec_preview
from max.spec.slo_plan import (
    SLO_PLAN_CSV_COLUMNS,
    SLO_PLAN_SCHEMA_VERSION,
    generate_slo_plan,
    render_slo_plan_csv,
    render_slo_plan_markdown,
)
from max.types.buildable_unit import BuildableCategory, BuildableUnit


def test_generate_slo_plan_has_stable_schema_shape(sample_unit, sample_evaluation) -> None:
    spec = generate_spec_preview(sample_unit, sample_evaluation)

    first = generate_slo_plan(sample_unit, sample_evaluation, spec)
    second = generate_slo_plan(sample_unit, sample_evaluation, spec)

    assert first == second
    assert first["schema_version"] == SLO_PLAN_SCHEMA_VERSION
    assert first["kind"] == "max.slo_plan"
    assert first["idea_id"] == "bu-test001"
    assert first["source"]["tact_spec_schema_version"] == "tact-spec-preview/v1"
    assert first["source"]["evaluation_available"] is True
    assert first["summary"] == {
        "title": "MCP Test Framework",
        "one_liner": "Standardized testing for MCP servers",
        "target_user": "MCP server maintainer",
        "buyer": "developer platform lead",
        "workflow_context": "pre-release CI validation",
        "primary_scope": "A CLI tool that validates MCP server implementations",
        "value_proposition": "Reduce bugs in MCP servers by 80%",
        "validation_plan": "run against five open-source MCP servers",
        "launch_tier": "production_candidate",
        "recommendation": "yes",
        "overall_score": 78.0,
    }
    assert set(first) == {
        "schema_version",
        "kind",
        "idea_id",
        "source",
        "summary",
        "objectives",
        "alerts",
        "error_budget_policy",
        "validation_steps",
        "gaps",
        "next_actions",
    }
    assert [item["type"] for item in first["objectives"]] == [
        "availability",
        "latency",
        "freshness",
        "support_response",
    ]
    assert first["objectives"][0]["target"] == "99.5%"
    assert first["objectives"][1]["target"] == "p95 <= 1500 ms"
    assert "signal:sig-test001" in first["objectives"][0]["evidence_refs"]
    assert any(alert["name"] == "known_risk_materialized" for alert in first["alerts"])
    assert any(alert["name"] == "budget_exhaustion_forecast" for alert in first["alerts"])
    assert first["error_budget_policy"]["budget_source_objective_id"] == "SLO1"
    assert first["gaps"] == []
    assert [step["id"] for step in first["validation_steps"]] == ["VAL1", "VAL2", "VAL3", "VAL4"]
    assert any(action["id"] == "NA6" for action in first["next_actions"])


def test_generate_slo_plan_is_json_serializable(sample_unit, sample_evaluation) -> None:
    plan = generate_slo_plan(sample_unit, sample_evaluation)

    assert json.loads(json.dumps(plan))["idea_id"] == "bu-test001"


def test_generate_slo_plan_degrades_with_explicit_gaps_for_sparse_inputs() -> None:
    sparse_unit = BuildableUnit(
        id="bu-sparse",
        title="Sparse Agent Helper",
        one_liner="Help agents do a task",
        category=BuildableCategory.AUTOMATION,
        problem="Agents need help",
        solution="",
        value_proposition="",
    )

    plan = generate_slo_plan(sparse_unit)

    assert plan["source"]["evaluation_available"] is False
    assert plan["source"]["tact_spec_available"] is False
    assert plan["summary"]["target_user"] == "both"
    assert plan["summary"]["buyer"] == "launch sponsor"
    assert plan["summary"]["launch_tier"] == "limited_pilot"
    assert plan["objectives"][0]["target"] == "99.0%"
    assert {gap["category"] for gap in plan["gaps"]} == {
        "missing_evaluation",
        "missing_tact_spec",
        "missing_workflow_context",
        "missing_validation_plan",
        "missing_evidence_refs",
        "missing_buyer",
    }
    assert any(alert["name"] == "readiness_gap_open" for alert in plan["alerts"])
    assert plan["validation_steps"][-1]["id"] == "VAL5"
    assert plan["next_actions"][0]["id"] == "NA0"


def test_render_slo_plan_markdown_is_deterministic(sample_unit, sample_evaluation) -> None:
    plan = generate_slo_plan(sample_unit, sample_evaluation)

    first = render_slo_plan_markdown(plan)
    second = render_slo_plan_markdown(plan)

    assert first == second
    assert first.startswith("# MCP Test Framework SLO Plan")
    assert f"- Schema version: {SLO_PLAN_SCHEMA_VERSION}" in first
    assert "## Objectives" in first
    assert "## Alerts" in first
    assert "## Error Budget Policy" in first
    assert "## Validation Steps" in first
    assert "## Gaps" in first
    assert "## Next Actions" in first
    assert "### SLO1: availability" in first
    assert "### AL1: availability_burn (critical)" in first
    assert "protocol churn" in first
    assert "signal:sig-test001" in first


def test_render_slo_plan_markdown_rejects_unsupported_format(sample_unit) -> None:
    plan = generate_slo_plan(sample_unit)

    with pytest.raises(ValueError, match="Unsupported SLO plan render format: json"):
        render_slo_plan_markdown(plan, output_format="json")


def test_render_slo_plan_csv_is_parseable_with_stable_operational_rows(
    sample_unit,
    sample_evaluation,
) -> None:
    plan = generate_slo_plan(sample_unit, sample_evaluation)

    first = render_slo_plan_csv(plan)
    second = render_slo_plan_csv(plan)
    reader = csv.DictReader(io.StringIO(first))
    rows = list(reader)

    assert first == second
    assert first.endswith("\n")
    assert reader.fieldnames == list(SLO_PLAN_CSV_COLUMNS)
    assert first.splitlines()[0] == ",".join(SLO_PLAN_CSV_COLUMNS)

    objective_row = next(
        row
        for row in rows
        if row["section"] == "objectives"
        and row["type"] == "service_objective"
        and row["item_id"] == "SLO1"
    )
    assert objective_row["idea_id"] == "bu-test001"
    assert objective_row["title"] == "MCP Test Framework"
    assert objective_row["launch_tier"] == "production_candidate"
    assert objective_row["name"] == "availability"
    assert objective_row["target"] == "99.5%"
    assert objective_row["measurement_window"] == "rolling 7 days during pilot, rolling 30 days after launch"
    assert objective_row["owner"] == "on_call_owner"
    assert "signal:sig-test001" in objective_row["evidence_refs"]

    indicator_row = next(
        row
        for row in rows
        if row["section"] == "objectives" and row["type"] == "indicator" and row["item_id"] == "SLO2"
    )
    assert indicator_row["objective_id"] == "SLO2"
    assert indicator_row["name"] == "latency"
    assert indicator_row["target"] == "p95 <= 1500 ms"
    assert indicator_row["indicator"] == "p95(workflow_response_time_ms)"
    assert indicator_row["source_refs"] == "unit.tech_approach; unit.suggested_stack"

    alert_row = next(row for row in rows if row["section"] == "alerts" and row["item_id"] == "AL1")
    assert alert_row["type"] == "alert_policy"
    assert alert_row["name"] == "availability_burn"
    assert alert_row["severity"] == "critical"
    assert alert_row["objective_id"] == "SLO1"
    assert "burns faster than 2x expected rate" in alert_row["condition"]
    assert alert_row["owner"] == "on_call_owner"

    policy_row = next(row for row in rows if row["section"] == "error_budget" and row["type"] == "policy")
    assert policy_row["item_id"] == "EBP1"
    assert policy_row["objective_id"] == "SLO1"
    assert policy_row["measurement_window"] == "monthly after launch; weekly during pilot"
    assert "0.5% monthly unavailability budget" in policy_row["policy"]

    cadence_row = next(row for row in rows if row["section"] == "operations" and row["type"] == "review_cadence")
    assert cadence_row["item_id"] == "EBP1-CADENCE"
    assert cadence_row["measurement_window"] == "monthly after launch; weekly during pilot"
    assert "Non-critical launches wait" in cadence_row["action"]


def test_slo_plan_is_importable_from_spec_package(sample_unit, sample_evaluation) -> None:
    plan = exported_generate(sample_unit, sample_evaluation)
    markdown = exported_render(plan)
    csv_text = exported_render_csv(plan)

    assert plan["schema_version"] == SLO_PLAN_SCHEMA_VERSION
    assert markdown.startswith("# MCP Test Framework SLO Plan")
    assert csv_text.startswith(",".join(SLO_PLAN_CSV_COLUMNS))
