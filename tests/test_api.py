"""Tests for the REST API endpoints."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from max.server.app import create_app
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode
from max.types.evaluation import DimensionScore, UtilityEvaluation
from max.types.insight import Insight, InsightCategory
from max.types.signal import Signal, SignalSourceType
from max.types.tact_spec import (
    TactArchitecture,
    TactGoal,
    TactProduct,
    TactRequirement,
    TactSpec,
    TactTechStack,
)


@pytest.fixture
def db_path(tmp_path):
    """Create a temp DB path and initialize schema."""
    path = str(tmp_path / "test_api.db")
    store = Store(db_path=path, wal_mode=True)
    store.close()
    return path


@pytest.fixture
def client(db_path):
    """TestClient with get_store overridden to use per-request connections."""
    from max.server.dependencies import get_store

    app = create_app()

    def override_get_store():
        store = Store(db_path=db_path, wal_mode=True)
        try:
            yield store
        finally:
            store.close()

    app.dependency_overrides[get_store] = override_get_store
    return TestClient(app)


@pytest.fixture
def seeded_db(db_path):
    """DB pre-populated with test data."""
    store = Store(db_path=db_path, wal_mode=True)

    signal = Signal(
        id="sig-api001",
        source_type=SignalSourceType.FORUM,
        source_adapter="test",
        title="Test Signal",
        content="Test content for API",
        url="https://example.com/test",
        tags=["test"],
        credibility=0.7,
    )
    store.insert_signal(signal)

    insight = Insight(
        id="ins-api001",
        category=InsightCategory.GAP,
        title="Test Insight",
        summary="A test insight for API testing",
        evidence=["sig-api001"],
        confidence=0.8,
        domains=["testing"],
    )
    store.insert_insight(insight)

    unit = BuildableUnit(
        id="bu-api001",
        title="Test Idea",
        one_liner="A test idea for the API",
        category=BuildableCategory.APPLICATION,
        ideation_mode=IdeationMode.DIRECT,
        problem="No test ideas",
        solution="Create a test idea",
        value_proposition="Better testing",
    )
    store.insert_buildable_unit(unit)

    def _score(val):
        return DimensionScore(value=val, confidence=0.7, reasoning="test")

    evaluation = UtilityEvaluation(
        buildable_unit_id="bu-api001",
        pain_severity=_score(8.0),
        addressable_scale=_score(7.0),
        build_effort=_score(7.5),
        composability=_score(8.5),
        competitive_density=_score(9.0),
        timing_fit=_score(8.0),
        compounding_value=_score(7.0),
        overall_score=78.0,
        strengths=["Good"],
        weaknesses=["Limited"],
        recommendation="yes",
        weights_used={"pain_severity": 0.20},
    )
    store.insert_evaluation(evaluation)
    store.close()
    return db_path


@pytest.fixture
def seeded_client(seeded_db):
    from max.server.dependencies import get_store

    app = create_app()

    def override():
        store = Store(db_path=seeded_db, wal_mode=True)
        try:
            yield store
        finally:
            store.close()

    app.dependency_overrides[get_store] = override
    return TestClient(app)


@pytest.fixture
def seeded_db_with_spec(seeded_db):
    """DB pre-populated with test data including a TactSpec."""
    store = Store(db_path=seeded_db, wal_mode=True)
    spec = TactSpec(
        buildable_unit_id="bu-api001",
        product=TactProduct(
            name="test-product",
            vision="A test product",
            goals=[TactGoal(id="G-1", description="Test goal", success_criteria="Passes")],
            tech_stack=TactTechStack(languages=["Python"], frameworks=["FastAPI"]),
        ),
        architecture=TactArchitecture(
            invariants=["Tests must pass"],
            conventions=["snake_case"],
        ),
        requirements=[
            TactRequirement(
                title="Core feature",
                priority="critical",
                description="Implement core",
                acceptance_criteria=["It works"],
            ),
        ],
    )
    store.insert_tact_spec(spec)
    store.close()
    return seeded_db


@pytest.fixture
def spec_client(seeded_db_with_spec):
    from max.server.dependencies import get_store

    app = create_app()

    def override():
        store = Store(db_path=seeded_db_with_spec, wal_mode=True)
        try:
            yield store
        finally:
            store.close()

    app.dependency_overrides[get_store] = override
    return TestClient(app)


@pytest.fixture
def multi_idea_db(db_path):
    """DB with multiple ideas in different statuses for filter testing."""
    store = Store(db_path=db_path, wal_mode=True)

    for i, status in enumerate(["draft", "evaluated", "approved"], start=1):
        unit = BuildableUnit(
            id=f"bu-multi{i:03d}",
            title=f"Idea {status}",
            one_liner=f"A {status} idea",
            category=BuildableCategory.CLI_TOOL,
            ideation_mode=IdeationMode.DIRECT,
            problem="Problem",
            solution="Solution",
            value_proposition="Value",
            status=status,
        )
        store.insert_buildable_unit(unit)

    store.close()
    return db_path


@pytest.fixture
def multi_idea_client(multi_idea_db):
    from max.server.dependencies import get_store

    app = create_app()

    def override():
        store = Store(db_path=multi_idea_db, wal_mode=True)
        try:
            yield store
        finally:
            store.close()

    app.dependency_overrides[get_store] = override
    return TestClient(app)


# ── Signal endpoints ────────────────────────────────────────────────


def test_list_signals_empty(client):
    resp = client.get("/api/v1/signals")
    assert resp.status_code == 200
    assert resp.json() == []


def test_create_signal(client):
    resp = client.post(
        "/api/v1/signals",
        json={
            "title": "New Signal",
            "content": "Signal content",
            "url": "https://example.com/new",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "New Signal"
    assert data["id"].startswith("sig-")


def test_list_signals_after_create(client):
    client.post(
        "/api/v1/signals",
        json={"title": "S1", "content": "C1", "url": "https://example.com/1"},
    )
    resp = client.get("/api/v1/signals")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_list_signals_seeded(seeded_client):
    resp = seeded_client.get("/api/v1/signals")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["id"] == "sig-api001"


def test_signal_response_schema(seeded_client):
    """Verify response contains all SignalResponse fields."""
    resp = seeded_client.get("/api/v1/signals")
    data = resp.json()[0]
    expected_keys = {
        "id", "source_type", "source_adapter", "title", "content",
        "url", "author", "published_at", "fetched_at", "tags",
        "credibility", "metadata",
    }
    assert set(data.keys()) == expected_keys
    assert data["source_type"] == "forum"
    assert data["source_adapter"] == "test"
    assert isinstance(data["tags"], list)
    assert isinstance(data["credibility"], float)


def test_create_signal_full_fields(client):
    """Verify all optional fields are returned when provided."""
    resp = client.post(
        "/api/v1/signals",
        json={
            "title": "Full Signal",
            "content": "Full content",
            "url": "https://example.com/full",
            "source_type": "registry",
            "source_adapter": "npm",
            "author": "tester",
            "tags": ["a", "b"],
            "credibility": 0.9,
            "metadata": {"key": "value"},
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["source_type"] == "registry"
    assert data["source_adapter"] == "npm"
    assert data["author"] == "tester"
    assert data["tags"] == ["a", "b"]
    assert data["credibility"] == 0.9
    assert data["metadata"]["key"] == "value"


# ── Insight endpoints ───────────────────────────────────────────────


def test_list_insights_empty(client):
    resp = client.get("/api/v1/insights")
    assert resp.status_code == 200
    assert resp.json() == []


def test_create_insight(client):
    resp = client.post(
        "/api/v1/insights",
        json={
            "title": "New Insight",
            "summary": "An insight from the API",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "New Insight"
    assert data["id"].startswith("ins-")


def test_list_insights_seeded(seeded_client):
    resp = seeded_client.get("/api/v1/insights")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["id"] == "ins-api001"
    assert data[0]["title"] == "Test Insight"


def test_insight_response_schema(seeded_client):
    """Verify response contains all InsightResponse fields."""
    resp = seeded_client.get("/api/v1/insights")
    data = resp.json()[0]
    expected_keys = {
        "id", "category", "title", "summary", "evidence",
        "confidence", "domains", "implications", "time_horizon",
        "created_at",
    }
    assert set(data.keys()) == expected_keys
    assert data["category"] == "gap"
    assert data["confidence"] == 0.8
    assert data["domains"] == ["testing"]
    assert isinstance(data["created_at"], str)


def test_create_insight_full_fields(client):
    """Create insight with all fields and verify response."""
    resp = client.post(
        "/api/v1/insights",
        json={
            "category": "trend",
            "title": "Full Insight",
            "summary": "Full summary",
            "evidence": ["sig-1", "sig-2"],
            "confidence": 0.95,
            "domains": ["ai", "devtools"],
            "implications": ["Big impact"],
            "time_horizon": "medium_term",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["category"] == "trend"
    assert data["evidence"] == ["sig-1", "sig-2"]
    assert data["confidence"] == 0.95
    assert data["time_horizon"] == "medium_term"


# ── Idea endpoints ──────────────────────────────────────────────────


def test_list_ideas_empty(client):
    resp = client.get("/api/v1/ideas")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_ideas_seeded(seeded_client):
    resp = seeded_client.get("/api/v1/ideas")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["id"] == "bu-api001"
    assert data[0]["score"] == 78.0


def test_list_ideas_filter_min_score(seeded_client):
    resp = seeded_client.get("/api/v1/ideas?min_score=90")
    assert resp.status_code == 200
    assert len(resp.json()) == 0

    resp = seeded_client.get("/api/v1/ideas?min_score=50")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_list_ideas_filter_status(multi_idea_client):
    """Filter ideas by status query parameter."""
    resp = multi_idea_client.get("/api/v1/ideas?status=draft")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["status"] == "draft"

    resp = multi_idea_client.get("/api/v1/ideas?status=evaluated")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["status"] == "evaluated"

    resp = multi_idea_client.get("/api/v1/ideas?status=nonexistent")
    assert resp.status_code == 200
    assert len(resp.json()) == 0


def test_get_idea(seeded_client):
    resp = seeded_client.get("/api/v1/ideas/bu-api001")
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Test Idea"
    assert data["evaluation"]["overall_score"] == 78.0
    assert data["evaluation"]["recommendation"] == "yes"


def test_get_idea_not_found(client):
    resp = client.get("/api/v1/ideas/nonexistent")
    assert resp.status_code == 404


def test_create_idea(client):
    resp = client.post(
        "/api/v1/ideas",
        json={
            "title": "API Created Idea",
            "one_liner": "Idea from the API",
            "problem": "Need more ideas",
            "solution": "Generate via API",
            "value_proposition": "Easier idea creation",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "API Created Idea"
    assert data["id"].startswith("bu-")
    assert data["status"] == "draft"


# ── Spec endpoint ───────────────────────────────────────────────────


def test_get_spec_not_found(seeded_client):
    resp = seeded_client.get("/api/v1/ideas/bu-api001/spec")
    assert resp.status_code == 404


def test_get_spec_exists(spec_client):
    """Verify spec is returned when one exists."""
    resp = spec_client.get("/api/v1/ideas/bu-api001/spec")
    assert resp.status_code == 200
    data = resp.json()
    assert data["buildable_unit_id"] == "bu-api001"
    assert data["product"]["name"] == "test-product"
    assert data["product"]["vision"] == "A test product"
    assert len(data["requirements"]) == 1
    assert data["requirements"][0]["title"] == "Core feature"


def test_get_spec_idea_not_found(client):
    """Verify 404 when the idea itself doesn't exist."""
    resp = client.get("/api/v1/ideas/nonexistent/spec")
    assert resp.status_code == 404


# ── Feedback endpoint ───────────────────────────────────────────────


def test_feedback(seeded_client):
    resp = seeded_client.post(
        "/api/v1/ideas/bu-api001/feedback",
        json={"outcome": "approved", "reason": "Great idea"},
    )
    assert resp.status_code == 201
    assert resp.json()["outcome"] == "approved"


def test_feedback_not_found(client):
    resp = client.post(
        "/api/v1/ideas/nonexistent/feedback",
        json={"outcome": "rejected"},
    )
    assert resp.status_code == 404


# ── Stats endpoint ──────────────────────────────────────────────────


def test_stats_empty(client):
    resp = client.get("/api/v1/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["signals_count"] == 0
    assert data["ideas_count"] == 0


def test_stats_seeded(seeded_client):
    resp = seeded_client.get("/api/v1/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["signals_count"] == 1
    assert data["insights_count"] == 1
    assert data["ideas_count"] == 1
    assert data["avg_score"] == 78.0


# ── Similarity endpoint ────────────────────────────────────────────


def test_similar_empty(client):
    resp = client.post(
        "/api/v1/similar",
        json={"text": "some text", "entity_type": "signal"},
    )
    assert resp.status_code == 200
    assert resp.json() == []


def test_similar_with_results(client):
    """Mock SemanticIndex to return similarity results."""
    mock_results = [("sig-001", 0.95), ("sig-002", 0.87)]

    with patch("max.embeddings.engine.SemanticIndex") as MockIndex:
        MockIndex.return_value.find_similar.return_value = mock_results

        resp = client.post(
            "/api/v1/similar",
            json={
                "text": "MCP server testing",
                "entity_type": "signal",
                "threshold": 0.8,
                "limit": 5,
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["entity_id"] == "sig-001"
    assert data[0]["score"] == 0.95
    assert data[1]["entity_id"] == "sig-002"
    assert data[1]["score"] == 0.87

    MockIndex.return_value.find_similar.assert_called_once_with(
        "MCP server testing", "signal", threshold=0.8, limit=5,
    )


# ── Schedule endpoints ──────────────────────────────────────────────


@pytest.fixture
def schedule_client(db_path):
    """TestClient with scheduler attached to app.state."""
    from max.server.dependencies import get_store
    from max.server.scheduler import Scheduler

    app = create_app()

    def override_get_store():
        store = Store(db_path=db_path, wal_mode=True)
        try:
            yield store
        finally:
            store.close()

    app.dependency_overrides[get_store] = override_get_store
    app.state.scheduler = Scheduler(
        interval_seconds=21600,
        enabled=True,
        pipeline_kwargs={"signal_limit": 30, "min_score": 50.0},
    )
    return TestClient(app)


def test_get_schedule(schedule_client):
    resp = schedule_client.get("/api/v1/schedule")
    assert resp.status_code == 200
    data = resp.json()
    assert data["enabled"] is True
    assert data["interval_seconds"] == 21600
    assert data["running"] is False
    assert data["run_count"] == 0


def test_update_schedule_disable(schedule_client):
    resp = schedule_client.post(
        "/api/v1/schedule",
        json={"enabled": False},
    )
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False


def test_update_schedule_interval(schedule_client):
    resp = schedule_client.post(
        "/api/v1/schedule",
        json={"interval_seconds": 3600},
    )
    assert resp.status_code == 200
    assert resp.json()["interval_seconds"] == 3600
