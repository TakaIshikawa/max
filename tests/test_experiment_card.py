"""Tests for deterministic experiment card generation."""

from __future__ import annotations

import csv
import json
from io import StringIO

from max.spec.experiment_card import (
    EXPERIMENT_CARD_SCHEMA_VERSION,
    generate_experiment_card,
    render_experiment_card_csv,
)


def test_generate_experiment_card_structures_validation_plan(sample_unit, sample_evaluation):
    card = generate_experiment_card(sample_unit, sample_evaluation)

    assert card["schema_version"] == EXPERIMENT_CARD_SCHEMA_VERSION
    assert card["kind"] == "max.experiment_card"
    assert card["idea_id"] == "bu-test001"
    assert card["source"]["evaluation_available"] is True
    assert card["source"]["recommendation"] == "yes"
    assert card["idea_summary"]["title"] == "MCP Test Framework"
    assert card["primary_hypothesis"].startswith("MCP server maintainer will try MCP Test Framework")
    assert card["target_participant"]["persona"] == "MCP server maintainer"
    assert card["target_participant"]["sample_size"] == 5
    assert card["minimum_viable_test"]["description"] == sample_unit.validation_plan
    assert card["minimum_viable_test"]["duration_days"] == 7
    assert [item["day"] for item in card["seven_day_execution_plan"]] == [
        "Day 1",
        "Day 2",
        "Day 3",
        "Day 4",
        "Day 5",
        "Day 6",
        "Day 7",
    ]
    assert any(item["id"] == "domain_risk_1" for item in card["riskiest_assumptions"])
    assert any(item["id"] == "evaluation_weakness_1" for item in card["riskiest_assumptions"])
    assert any(metric["metric"] == "workflow_commitment" for metric in card["success_metrics"])
    assert set(card["decision_rules"]) == {"proceed", "iterate", "stop"}


def test_generate_experiment_card_missing_evaluation_uses_demand_fallback(sample_unit):
    unit = sample_unit.model_copy(
        update={
            "specific_user": "",
            "buyer": "",
            "workflow_context": "",
            "validation_plan": "",
            "domain_risks": [],
        }
    )

    card = generate_experiment_card(unit)

    assumption_ids = [item["id"] for item in card["riskiest_assumptions"]]
    assert card["source"]["evaluation_available"] is False
    assert "missing_evaluation" in assumption_ids
    assert "missing_specific_user" in assumption_ids
    assert "missing_buyer" in assumption_ids
    assert "missing_workflow_context" in assumption_ids
    assert card["target_participant"]["persona"] == "human or agent workflow owner"
    assert card["minimum_viable_test"]["type"] == "concierge_workflow"
    assert "Simulate MCP Test Framework manually" in card["minimum_viable_test"]["description"]


def test_generate_experiment_card_is_json_serializable(sample_unit, sample_evaluation):
    card = generate_experiment_card(sample_unit, sample_evaluation)

    assert json.loads(json.dumps(card))["kind"] == "max.experiment_card"


def test_render_experiment_card_csv_structure(sample_unit, sample_evaluation):
    card = generate_experiment_card(sample_unit, sample_evaluation)

    csv_output = render_experiment_card_csv(card)

    # Parse CSV
    reader = csv.DictReader(StringIO(csv_output))
    rows = list(reader)

    # Should have exactly one row
    assert len(rows) == 1
    row = rows[0]

    # Verify all expected columns are present
    assert "schema_version" in row
    assert "kind" in row
    assert "idea_id" in row
    assert "title" in row
    assert "primary_hypothesis" in row
    assert "target_persona" in row
    assert "target_buyer" in row
    assert "workflow_context" in row
    assert "sample_size" in row
    assert "duration_days" in row
    assert "test_type" in row
    assert "test_description" in row
    assert "riskiest_assumptions" in row
    assert "success_metrics" in row
    assert "failure_signals" in row
    assert "recruitment_channels" in row
    assert "success_criteria" in row
    assert "rollback_triggers" in row
    assert "learnings_capture" in row


def test_render_experiment_card_csv_metadata(sample_unit, sample_evaluation):
    card = generate_experiment_card(sample_unit, sample_evaluation)

    csv_output = render_experiment_card_csv(card)

    # Parse CSV
    reader = csv.DictReader(StringIO(csv_output))
    row = next(reader)

    # Verify core metadata
    assert row["schema_version"] == "max-experiment-card/v1"
    assert row["kind"] == "max.experiment_card"
    assert row["idea_id"] == "bu-test001"
    assert row["title"] == "MCP Test Framework"
    assert row["target_persona"] == "MCP server maintainer"
    assert row["sample_size"] == "5"
    assert row["duration_days"] == "7"
    assert "MCP server maintainer will try MCP Test Framework" in row["primary_hypothesis"]


def test_render_experiment_card_csv_experiment_details(sample_unit, sample_evaluation):
    card = generate_experiment_card(sample_unit, sample_evaluation)

    csv_output = render_experiment_card_csv(card)

    # Parse CSV
    reader = csv.DictReader(StringIO(csv_output))
    row = next(reader)

    # Verify test design
    assert row["test_type"] == "scripted_validation"
    assert row["test_description"]
    assert row["workflow_context"]
    assert row["target_buyer"]

    # Verify success metrics are formatted correctly
    assert "workflow_commitment" in row["success_metrics"]
    assert "|" in row["success_metrics"]  # Separator between metrics

    # Verify failure signals are formatted correctly
    assert row["failure_signals"]
    assert "|" in row["failure_signals"]  # Separator between signals

    # Verify riskiest assumptions are present
    assert "domain_risk_1" in row["riskiest_assumptions"]
    assert "|" in row["riskiest_assumptions"]  # Separator between assumptions


def test_render_experiment_card_csv_criteria_and_triggers(sample_unit, sample_evaluation):
    card = generate_experiment_card(sample_unit, sample_evaluation)

    csv_output = render_experiment_card_csv(card)

    # Parse CSV
    reader = csv.DictReader(StringIO(csv_output))
    row = next(reader)

    # Verify success criteria (proceed decision rule)
    assert row["success_criteria"]
    assert "commitments" in row["success_criteria"].lower()

    # Verify rollback triggers (stop decision rule)
    assert row["rollback_triggers"]
    assert "stop" in row["rollback_triggers"].lower() or "do not build" in row["rollback_triggers"].lower()

    # Verify learnings capture (instrumentation notes)
    assert row["learnings_capture"]
    assert "|" in row["learnings_capture"]  # Separator between notes


def test_render_experiment_card_csv_recruitment_channels(sample_unit, sample_evaluation):
    card = generate_experiment_card(sample_unit, sample_evaluation)

    csv_output = render_experiment_card_csv(card)

    # Parse CSV
    reader = csv.DictReader(StringIO(csv_output))
    row = next(reader)

    # Verify recruitment channels
    assert row["recruitment_channels"]
    # Should have multiple channels separated by |
    channels = row["recruitment_channels"].split("|")
    assert len(channels) >= 1
