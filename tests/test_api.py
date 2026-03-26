"""Tests for the REST API endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from max.server.app import create_app
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode
from max.types.evaluation import DimensionScore, UtilityEvaluation
from max.types.insight import Insight, InsightCategory
from max.types.signal import Signal, SignalSourceType


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
