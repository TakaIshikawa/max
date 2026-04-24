"""Tests for MCP review gate tool and resource exposure."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from max.server.app import create_app
from max.server.dependencies import get_store
from max.server.mcp_tools import (
    get_review_gate_decision,
    review_gate_detail,
    set_store_factory,
)
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode
from max.types.evaluation import DimensionScore, UtilityEvaluation


CORE_REVIEW_GATE_FIELDS = [
    "decision",
    "confidence",
    "blocking_reasons",
    "warnings",
    "required_remediations",
    "evidence_used",
]


@pytest.fixture
def mcp_review_gate_db(tmp_path):
    db_path = str(tmp_path / "test_mcp_review_gate.db")
    store = Store(db_path=db_path, wal_mode=True)
    store.close()

    set_store_factory(lambda: Store(db_path=db_path, wal_mode=True))
    yield db_path
    set_store_factory(lambda: Store(wal_mode=True))


@pytest.fixture
def seeded_review_gate_db(mcp_review_gate_db):
    store = Store(db_path=mcp_review_gate_db, wal_mode=True)
    try:
        unit = BuildableUnit(
            id="bu-review-gate-mcp",
            title="Review Gate MCP Idea",
            one_liner="Expose review gate decisions through MCP",
            category=BuildableCategory.CLI_TOOL,
            ideation_mode=IdeationMode.DIRECT,
            problem="Agents cannot inspect deterministic review gate decisions.",
            solution="Expose the same review gate payload through an MCP tool and resource.",
            target_users="agent consumers",
            specific_user="spec generation agent",
            buyer="platform lead",
            workflow_context="pre-publication spec review",
            value_proposition="Agents can avoid generating specs for blocked ideas.",
            validation_plan="Compare MCP and REST review gate payloads.",
            domain_risks=["policy drift"],
            evidence_rationale="REST already exposes the deterministic decision.",
            inspiring_insights=["ins-review-gate"],
            evidence_signals=["sig-review-gate"],
            tech_approach="Add a narrow MCP wrapper around the existing builder.",
            suggested_stack={"language": "python"},
            prior_art_status="clear",
            domain="developer-tools",
            status="evaluated",
        )
        store.insert_buildable_unit(unit)
        store.insert_evaluation(_evaluation(unit.id))
    finally:
        store.close()
    return mcp_review_gate_db


def _dim(value: float = 8.0) -> DimensionScore:
    return DimensionScore(value=value, confidence=0.8, reasoning="test")


def _evaluation(unit_id: str) -> UtilityEvaluation:
    return UtilityEvaluation(
        buildable_unit_id=unit_id,
        pain_severity=_dim(8.0),
        addressable_scale=_dim(8.0),
        build_effort=_dim(8.0),
        composability=_dim(8.0),
        competitive_density=_dim(8.0),
        timing_fit=_dim(8.0),
        compounding_value=_dim(8.0),
        overall_score=84.0,
        recommendation="yes",
        strengths=["Clear agent consumer"],
        weaknesses=["Needs MCP exposure"],
        weights_used={"pain_severity": 0.20},
    )


def _rest_review_gate(db_path: str, idea_id: str) -> dict:
    app = create_app()

    def override_get_store():
        store = Store(db_path=db_path, wal_mode=True)
        try:
            yield store
        finally:
            store.close()

    app.dependency_overrides[get_store] = override_get_store
    try:
        response = TestClient(app).get(f"/api/v1/ideas/{idea_id}/review-gate")
        response.raise_for_status()
        return response.json()
    finally:
        app.dependency_overrides.clear()


def test_get_review_gate_decision_matches_rest_core_fields(seeded_review_gate_db):
    idea_id = "bu-review-gate-mcp"

    mcp_result = get_review_gate_decision(idea_id=idea_id)
    rest_result = _rest_review_gate(seeded_review_gate_db, idea_id)

    assert mcp_result["schema_version"] == rest_result["schema_version"]
    assert mcp_result["kind"] == rest_result["kind"]
    assert mcp_result["idea_id"] == idea_id
    for field in CORE_REVIEW_GATE_FIELDS:
        assert mcp_result[field] == rest_result[field]


def test_get_review_gate_decision_accepts_threshold_overrides(seeded_review_gate_db):
    result = get_review_gate_decision(
        idea_id="bu-review-gate-mcp",
        approve_threshold=99.0,
        reject_threshold=20.0,
        min_readiness=50.0,
        approve_readiness=99.0,
        high_blast_radius=99.0,
        medium_blast_radius=99.0,
    )

    utility_evidence = next(
        item for item in result["evidence_used"] if item["source"] == "utility_evaluation"
    )
    assert utility_evidence["details"]["approve_threshold"] == 99.0
    assert utility_evidence["details"]["reject_threshold"] == 20.0
    assert result["decision"] == "needs_revision"


def test_get_review_gate_decision_unknown_idea_returns_mcp_error(mcp_review_gate_db):
    result = get_review_gate_decision(idea_id="missing-review-gate")

    assert result["error"] == "Idea not found: missing-review-gate"
    assert result["code"] == 404
    assert result["details"] == {
        "resource_type": "buildable_unit",
        "resource_id": "missing-review-gate",
    }


def test_review_gate_resource_returns_pretty_printed_json(seeded_review_gate_db):
    rendered = review_gate_detail("bu-review-gate-mcp")
    payload = json.loads(rendered)

    assert rendered.startswith("{\n  ")
    assert payload["idea_id"] == "bu-review-gate-mcp"
    assert payload["kind"] == "max.review_gate"
    for field in CORE_REVIEW_GATE_FIELDS:
        assert field in payload

