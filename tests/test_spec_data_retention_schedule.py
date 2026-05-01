"""Tests for TactSpec data retention schedule generation."""

from __future__ import annotations

import json

import pytest

from max.spec import generate_data_retention_schedule as exported_generate
from max.spec import render_data_retention_schedule_markdown as exported_render
from max.spec.data_retention_schedule import (
    DATA_RETENTION_SCHEDULE_SCHEMA_VERSION,
    generate_data_retention_schedule,
    render_data_retention_schedule_markdown,
)
from max.spec.generator import generate_spec_preview
from max.types.buildable_unit import BuildableCategory, BuildableUnit


def test_generate_data_retention_schedule_has_stable_schema_shape(
    sample_unit, sample_evaluation
) -> None:
    spec = generate_spec_preview(sample_unit, sample_evaluation)
    spec["solution"]["technical_approach"] = (
        "TypeScript CLI stores audit logs, GitHub webhook payloads, OpenAI prompt summaries, "
        "CSV exports, OAuth tokens, and customer workflow records in Postgres."
    )
    spec["execution"]["mvp_scope"].append(
        "Retain pilot logs for 30 days, expire exports after 14 days, and delete workspace records on request."
    )

    first = generate_data_retention_schedule(sample_unit, sample_evaluation, spec)
    second = generate_data_retention_schedule(sample_unit, sample_evaluation, spec)

    assert first == second
    assert first["schema_version"] == DATA_RETENTION_SCHEDULE_SCHEMA_VERSION
    assert first["kind"] == "max.spec.data_retention_schedule"
    assert first["idea_id"] == "bu-test001"
    assert first["source"]["tact_spec_schema_version"] == "tact-spec-preview/v1"
    assert first["source"]["evaluation_available"] is True
    assert first["summary"]["title"] == "MCP Test Framework"
    assert first["summary"]["retention_gate"] == "ready_with_owner_approval"
    assert set(first) == {
        "schema_version",
        "kind",
        "idea_id",
        "source",
        "summary",
        "retention_context",
        "data_categories",
        "retention_rules",
        "deletion_triggers",
        "owners",
        "gaps",
        "missing_inputs",
        "next_actions",
    }
    assert [item["id"] for item in first["data_categories"]] == [
        "customer_identifiers",
        "workflow_records",
        "authentication_and_access",
        "logs_and_telemetry",
        "ai_inputs_outputs",
        "exports_and_reports",
    ]
    assert all(rule["retention_period"] for rule in first["retention_rules"])
    assert all(rule["deletion_trigger"] for rule in first["retention_rules"])
    assert all(rule["owner"] for rule in first["retention_rules"])
    assert all(rule["legal_privacy_rationale"] for rule in first["retention_rules"])
    assert any(rule["data_category_id"] == "backups_caches_and_derived_copies" for rule in first["retention_rules"])
    assert any(rule["data_category_id"] == "third_party_transfers" for rule in first["retention_rules"])
    assert any(trigger["name"] == "integration_disconnected" for trigger in first["deletion_triggers"])
    assert {owner["owner"] for owner in first["owners"]} >= {
        "data_owner",
        "engineering_owner",
        "integration_owner",
        "platform_owner",
    }
    assert first["gaps"] == []
    assert "signal:sig-test001" in first["retention_rules"][0]["evidence_refs"]


def test_generate_data_retention_schedule_is_json_serializable(sample_unit) -> None:
    schedule = generate_data_retention_schedule(sample_unit)

    assert json.loads(json.dumps(schedule))["idea_id"] == "bu-test001"


def test_generate_data_retention_schedule_degrades_for_sparse_inputs() -> None:
    sparse_unit = BuildableUnit(
        id="bu-sparse",
        title="Sparse Agent Helper",
        one_liner="Help agents do a task",
        category=BuildableCategory.AUTOMATION,
        problem="Agents need help",
        solution="",
        value_proposition="",
    )

    schedule = generate_data_retention_schedule(sparse_unit)

    assert schedule["source"]["evaluation_available"] is False
    assert schedule["source"]["tact_spec_available"] is False
    assert schedule["summary"]["target_user"] == "both"
    assert schedule["summary"]["buyer"] == "launch sponsor"
    assert schedule["summary"]["workflow_context"] == "Sparse Agent Helper workflow"
    assert schedule["summary"]["retention_gate"] == "retention_inputs_required"
    assert [item["id"] for item in schedule["data_categories"]] == ["unspecified_product_data"]
    assert schedule["retention_rules"][0]["retention_period"] == (
        "30-90 days until the data owner approves a field-level schedule"
    )
    assert {gap["category"] for gap in schedule["gaps"]} == {
        "missing_evaluation",
        "missing_tact_spec",
        "missing_workflow_context",
        "missing_explicit_retention",
        "missing_evidence_refs",
        "missing_validation_plan",
    }
    assert "retention_policy" in schedule["missing_inputs"]
    assert schedule["next_actions"][0]["id"] == "NA0"


def test_render_data_retention_schedule_markdown_includes_rules_and_missing_inputs() -> None:
    sparse_unit = BuildableUnit(
        id="bu-sparse",
        title="Sparse Agent Helper",
        one_liner="Help agents do a task",
        category=BuildableCategory.AUTOMATION,
        problem="Agents need help",
        solution="",
        value_proposition="",
    )
    schedule = generate_data_retention_schedule(sparse_unit)

    first = render_data_retention_schedule_markdown(schedule)
    second = render_data_retention_schedule_markdown(schedule)

    assert first == second
    assert first.startswith("# Sparse Agent Helper Data Retention Schedule")
    assert f"- Schema version: {DATA_RETENTION_SCHEDULE_SCHEMA_VERSION}" in first
    assert "- TactSpec schema: none" in first
    assert "## Data Categories" in first
    assert "## Retention Rules" in first
    assert "## Deletion Triggers" in first
    assert "## Owners" in first
    assert "## Missing Input Notes" in first
    assert "## Next Actions" in first
    assert "### RET01: Unspecified product, user, or operational data" in first
    assert "30-90 days until the data owner approves a field-level schedule" in first
    assert "missing_explicit_retention" in first
    assert "retention_policy" in first


def test_render_data_retention_schedule_markdown_rejects_unsupported_format(sample_unit) -> None:
    schedule = generate_data_retention_schedule(sample_unit)

    with pytest.raises(ValueError, match="Unsupported data retention schedule render format: json"):
        render_data_retention_schedule_markdown(schedule, output_format="json")


def test_data_retention_schedule_is_importable_from_spec_package(
    sample_unit, sample_evaluation
) -> None:
    schedule = exported_generate(sample_unit, sample_evaluation)
    markdown = exported_render(schedule)

    assert schedule["schema_version"] == DATA_RETENTION_SCHEDULE_SCHEMA_VERSION
    assert markdown.startswith("# MCP Test Framework Data Retention Schedule")
