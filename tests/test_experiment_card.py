"""Tests for deterministic experiment card generation."""

from __future__ import annotations

import json

from max.spec.experiment_card import (
    EXPERIMENT_CARD_SCHEMA_VERSION,
    generate_experiment_card,
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
