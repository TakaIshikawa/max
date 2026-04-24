"""Tests for validation experiment MCP tools."""

from __future__ import annotations

import json

import pytest

from max.server.mcp_tools import (
    create_validation_experiment,
    get_validation_experiment,
    list_validation_experiments,
    set_store_factory,
    update_validation_experiment,
    validation_experiment_detail,
    validation_experiments_for_idea_detail,
)
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode


@pytest.fixture
def mcp_validation_db(tmp_path):
    """Create temp DB and configure mcp_tools to use it."""
    db_path = str(tmp_path / "test_mcp_validation.db")
    store = Store(db_path=db_path, wal_mode=True)
    store.close()

    set_store_factory(lambda: Store(db_path=db_path, wal_mode=True))
    yield db_path
    set_store_factory(lambda: Store(wal_mode=True))


@pytest.fixture
def seeded_idea(mcp_validation_db):
    store = Store(db_path=mcp_validation_db, wal_mode=True)
    unit = BuildableUnit(
        id="bu-mcp-vexp001",
        title="MCP validation loops",
        one_liner="Manage validation experiments over MCP",
        category=BuildableCategory.APPLICATION,
        ideation_mode=IdeationMode.DIRECT,
        problem="Agents cannot manage validation follow-up.",
        solution="Expose validation experiment MCP tools.",
        value_proposition="Agents can close validation loops.",
        domain="developer-tools",
    )
    store.insert_buildable_unit(unit)
    store.close()
    return unit


def test_mcp_validation_experiment_lifecycle(seeded_idea):
    created = create_validation_experiment(
        seeded_idea.id,
        {
            "hypothesis": "Agents will create clearer next steps.",
            "method": "Concierge validation",
            "target_sample_size": 5,
            "success_metric": "Four of five agents update status correctly.",
            "status": "planned",
            "due_date": "2026-05-01",
            "evidence_urls": ["https://example.com/interview-notes"],
            "confidence_delta": 0.1,
        },
    )

    assert created["idea_id"] == seeded_idea.id
    assert created["hypothesis"] == "Agents will create clearer next steps."
    assert created["evidence_urls"] == ["https://example.com/interview-notes"]

    listed = list_validation_experiments(seeded_idea.id)
    assert listed["idea_id"] == seeded_idea.id
    assert listed["experiments"] == [created]

    fetched = get_validation_experiment(created["id"])
    assert fetched == created

    updated = update_validation_experiment(
        created["id"],
        {
            "status": "completed",
            "completed_at": "2026-05-02",
            "result_summary": "Agents completed the loop.",
            "confidence_delta": 0.25,
        },
    )
    assert updated["status"] == "completed"
    assert updated["result_summary"] == "Agents completed the loop."
    assert updated["confidence_delta"] == 0.25


def test_mcp_validation_experiment_missing_idea_returns_error(mcp_validation_db):
    listed = list_validation_experiments("missing-idea")
    assert listed["error"] == "Idea not found: missing-idea"
    assert listed["code"] == 404
    assert listed["details"]["resource_type"] == "buildable_unit"
    assert listed["details"]["resource_id"] == "missing-idea"

    created = create_validation_experiment(
        "missing-idea",
        {
            "hypothesis": "Missing ideas should not raise.",
            "method": "Tool call",
            "success_metric": "MCP error dictionary returned.",
        },
    )
    assert created["error"] == "Idea not found: missing-idea"
    assert created["code"] == 404
    assert created["details"]["resource_type"] == "buildable_unit"
    assert created["details"]["resource_id"] == "missing-idea"


def test_mcp_validation_experiment_missing_experiment_returns_error(mcp_validation_db):
    fetched = get_validation_experiment("missing-vexp")
    assert fetched["error"] == "Validation experiment not found: missing-vexp"
    assert fetched["code"] == 404
    assert fetched["details"]["resource_type"] == "validation_experiment"
    assert fetched["details"]["resource_id"] == "missing-vexp"

    updated = update_validation_experiment("missing-vexp", {"status": "completed"})
    assert updated["error"] == "Validation experiment not found: missing-vexp"
    assert updated["code"] == 404
    assert updated["details"]["resource_type"] == "validation_experiment"
    assert updated["details"]["resource_id"] == "missing-vexp"


def test_validation_experiment_resources_return_json(seeded_idea):
    created = create_validation_experiment(
        seeded_idea.id,
        {
            "hypothesis": "Resources expose validation loops.",
            "method": "Resource read",
            "success_metric": "JSON payload includes experiment.",
        },
    )

    list_payload = json.loads(validation_experiments_for_idea_detail(seeded_idea.id))
    assert list_payload["idea_id"] == seeded_idea.id
    assert list_payload["experiments"][0]["id"] == created["id"]

    detail_payload = json.loads(validation_experiment_detail(created["id"]))
    assert detail_payload["id"] == created["id"]
    assert detail_payload["success_metric"] == "JSON payload includes experiment."
