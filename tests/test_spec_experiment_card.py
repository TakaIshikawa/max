"""Tests for experiment card CSV export."""

from __future__ import annotations

import csv
from io import StringIO

from max.spec.experiment_card import (
    EXPERIMENT_CARD_CSV_COLUMNS,
    EXPERIMENT_CARD_SCHEMA_VERSION,
    generate_experiment_card,
    render_experiment_card_csv,
)


def test_render_experiment_card_csv_includes_all_columns(sample_unit, sample_evaluation):
    card = generate_experiment_card(sample_unit, sample_evaluation)
    csv_output = render_experiment_card_csv(card)

    reader = csv.DictReader(StringIO(csv_output))
    rows = list(reader)

    assert len(rows) == 1
    row = rows[0]

    # Verify all expected columns are present
    assert set(row.keys()) == set(EXPERIMENT_CARD_CSV_COLUMNS)


def test_render_experiment_card_csv_core_metadata(sample_unit, sample_evaluation):
    card = generate_experiment_card(sample_unit, sample_evaluation)
    csv_output = render_experiment_card_csv(card)

    reader = csv.DictReader(StringIO(csv_output))
    row = next(reader)

    assert row["schema_version"] == EXPERIMENT_CARD_SCHEMA_VERSION
    assert row["kind"] == "max.experiment_card"
    assert row["idea_id"] == "bu-test001"
    assert row["idea_title"] == "MCP Test Framework"
    assert "MCP server maintainer will try MCP Test Framework" in row["primary_hypothesis"]


def test_render_experiment_card_csv_target_participant_fields(sample_unit, sample_evaluation):
    card = generate_experiment_card(sample_unit, sample_evaluation)
    csv_output = render_experiment_card_csv(card)

    reader = csv.DictReader(StringIO(csv_output))
    row = next(reader)

    assert row["target_persona"] == "MCP server maintainer"
    assert row["sample_size"] == "5"


def test_render_experiment_card_csv_test_design_fields(sample_unit, sample_evaluation):
    card = generate_experiment_card(sample_unit, sample_evaluation)
    csv_output = render_experiment_card_csv(card)

    reader = csv.DictReader(StringIO(csv_output))
    row = next(reader)

    assert row["test_type"] == "scripted_validation"
    assert row["test_description"] == "run against five open-source MCP servers"
    assert row["duration_days"] == "7"


def test_render_experiment_card_csv_success_metrics(sample_unit, sample_evaluation):
    card = generate_experiment_card(sample_unit, sample_evaluation)
    csv_output = render_experiment_card_csv(card)

    reader = csv.DictReader(StringIO(csv_output))
    row = next(reader)

    metrics = row["success_metrics"]
    assert "qualified_participants:" in metrics
    assert "problem_confirmation:" in metrics
    assert "workflow_commitment:" in metrics
    # Metrics separated by pipe character
    assert "|" in metrics


def test_render_experiment_card_csv_failure_signals(sample_unit, sample_evaluation):
    card = generate_experiment_card(sample_unit, sample_evaluation)
    csv_output = render_experiment_card_csv(card)

    reader = csv.DictReader(StringIO(csv_output))
    row = next(reader)

    signals = row["failure_signals"]
    assert "weak_recruiting:" in signals
    assert "low_pain:" in signals
    assert "no_commitment:" in signals
    assert "|" in signals


def test_render_experiment_card_csv_decision_rules(sample_unit, sample_evaluation):
    card = generate_experiment_card(sample_unit, sample_evaluation)
    csv_output = render_experiment_card_csv(card)

    reader = csv.DictReader(StringIO(csv_output))
    row = next(reader)

    assert "Build the MVP if" in row["decision_proceed"]
    assert "Revise target user" in row["decision_iterate"]
    assert "Do not build if" in row["decision_stop"]


def test_render_experiment_card_csv_riskiest_assumptions(sample_unit, sample_evaluation):
    card = generate_experiment_card(sample_unit, sample_evaluation)
    csv_output = render_experiment_card_csv(card)

    reader = csv.DictReader(StringIO(csv_output))
    row = next(reader)

    assumptions = row["riskiest_assumptions"]
    # Should include domain risk and evaluation weakness
    assert "protocol churn" in assumptions.lower() or "domain" in assumptions.lower()
    assert "|" in assumptions  # Multiple assumptions separated by pipe


def test_render_experiment_card_csv_recruitment_channels(sample_unit, sample_evaluation):
    card = generate_experiment_card(sample_unit, sample_evaluation)
    csv_output = render_experiment_card_csv(card)

    reader = csv.DictReader(StringIO(csv_output))
    row = next(reader)

    channels = row["recruitment_channels"]
    assert len(channels) > 0
    # Should have channel names separated by pipe if multiple
    if "|" in channels:
        channel_list = channels.split(" | ")
        assert len(channel_list) > 1


def test_render_experiment_card_csv_seven_day_plan(sample_unit, sample_evaluation):
    card = generate_experiment_card(sample_unit, sample_evaluation)
    csv_output = render_experiment_card_csv(card)

    reader = csv.DictReader(StringIO(csv_output))
    row = next(reader)

    plan = row["seven_day_plan"]
    # Should have all 7 days
    assert "Day 1:" in plan
    assert "Day 7:" in plan
    assert "|" in plan  # Days separated by pipe


def test_render_experiment_card_csv_missing_evaluation(sample_unit):
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
    csv_output = render_experiment_card_csv(card)

    reader = csv.DictReader(StringIO(csv_output))
    row = next(reader)

    assert row["idea_id"] == "bu-test001"
    assert row["test_type"] == "concierge_workflow"
    assert "Simulate MCP Test Framework manually" in row["test_description"]


def test_render_experiment_card_csv_empty_card_returns_headers():
    csv_output = render_experiment_card_csv({})

    reader = csv.DictReader(StringIO(csv_output))
    rows = list(reader)

    assert len(rows) == 1
    row = rows[0]
    # All fields should be empty strings
    assert all(value == "" for value in row.values())


def test_render_experiment_card_csv_handles_none_values(sample_unit):
    card = generate_experiment_card(sample_unit)
    # Modify card to have None values
    card["primary_hypothesis"] = None
    card["riskiest_assumptions"] = None

    csv_output = render_experiment_card_csv(card)

    reader = csv.DictReader(StringIO(csv_output))
    row = next(reader)

    # Should handle None gracefully with empty strings
    assert row["primary_hypothesis"] == ""
    assert row["riskiest_assumptions"] == ""
