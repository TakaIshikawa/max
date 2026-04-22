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
        inspiring_insights=["ins-api001"],
        evidence_signals=["sig-api001"],
    )
    store.insert_buildable_unit(unit)

    from max.analysis.portfolio_synthesis import Candidate, ProjectBrief

    store.insert_design_brief(
        ProjectBrief(
            title="Test Design Brief",
            domain="testing",
            theme="api-testing",
            lead=Candidate(unit=unit),
            readiness_score=82.0,
            why_this_now="API clients need a stable handoff.",
            merged_product_concept="A testable design brief export.",
            synthesis_rationale="Single approved source idea.",
            mvp_scope=["Export packet"],
            first_milestones=["Add endpoint"],
            validation_plan="Call the API.",
            risks=["None"],
            source_idea_ids=["bu-api001"],
        )
    )

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
    from max.quality.scorer import DomainQualityScore

    store.insert_domain_quality_score(
        DomainQualityScore(
            buildable_unit_id="bu-api001",
            domain="testing",
            profile_name="test",
            rubric_version="v1",
            dimensions={"buyer_clarity": 8.0},
            overall_score=76.0,
            passed_gate=True,
            rejection_tags=[],
            reasoning="Specific test idea.",
        )
    )
    store.insert_domain_quality_memory(
        domain="testing",
        outcome="approved",
        pattern="Test Idea: A test idea for the API",
        source_idea_id="bu-api001",
        tags=[],
        score=76.0,
        notes="seeded",
    )
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


# ── Profile endpoints ───────────────────────────────────────────────


def _profile_endpoint_fixture(name: str, domain_name: str):
    from max.profiles.schema import DomainContext, EvaluationConfig, PipelineProfile, SourceConfig

    return PipelineProfile(
        name=name,
        domain=DomainContext(
            name=domain_name,
            description=f"{domain_name} domain",
            categories=["application", "cli_tool"],
            target_user_types=["developers"],
            extra_instructions="Ship practical tools.",
            target_segments=["platform teams"],
            workflows=["triage"],
            buyer_roles=["engineering leaders"],
            hard_constraints=["no PHI"],
            bad_idea_patterns=["generic dashboards"],
            good_idea_criteria=["clear buyer"],
        ),
        sources=[
            SourceConfig(adapter="hackernews", weight=1.5),
            SourceConfig(adapter="reddit", enabled=False, params={"subreddits": ["programming"]}),
        ],
        evaluation=EvaluationConfig(weight_profile="agent_first", min_score=68.0),
        output_dir=".custom-output",
        signal_limit=42,
        ideation_mode="refinement",
        quality_loop_enabled=True,
        draft_count=6,
    )


def test_list_profiles_returns_profile_summaries(client):
    profiles = {
        "devtools": _profile_endpoint_fixture("devtools", "developer-tools"),
        "healthcare": _profile_endpoint_fixture("healthcare", "healthcare"),
    }

    with (
        patch("max.profiles.loader.list_profiles", return_value=list(profiles)),
        patch("max.profiles.loader.load_profile", side_effect=lambda name: profiles[name]),
    ):
        resp = client.get("/api/v1/profiles")

    assert resp.status_code == 200
    data = resp.json()
    assert [profile["name"] for profile in data] == ["devtools", "healthcare"]
    assert data[0] == {
        "name": "devtools",
        "domain": "developer-tools",
        "description": "developer-tools domain",
        "enabled_source_count": 1,
        "signal_limit": 42,
        "min_score": 68.0,
        "weight_profile": "agent_first",
        "ideation_mode": "refinement",
        "quality_loop_enabled": True,
    }


def test_get_profile_returns_profile_detail(client):
    profile = _profile_endpoint_fixture("devtools", "developer-tools")

    with patch("max.profiles.loader.load_profile", return_value=profile):
        resp = client.get("/api/v1/profiles/devtools")

    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "devtools"
    assert data["domain"]["name"] == "developer-tools"
    assert data["domain"]["target_segments"] == ["platform teams"]
    assert data["sources"][0]["adapter"] == "hackernews"
    assert data["sources"][1]["enabled"] is False
    assert data["sources"][1]["params"] == {"subreddits": ["programming"]}
    assert data["evaluation"] == {
        "weight_profile": "agent_first",
        "custom_weights": None,
        "min_score": 68.0,
    }
    assert data["output_dir"] == ".custom-output"
    assert data["draft_count"] == 6


def test_get_profile_returns_404_for_unknown_profile(client):
    with patch("max.profiles.loader.load_profile", side_effect=FileNotFoundError("missing")):
        resp = client.get("/api/v1/profiles/missing")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Profile not found: missing"


# ── Signal endpoints ────────────────────────────────────────────────


def test_list_signals_empty(client):
    resp = client.get("/api/v1/signals")
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["pagination"]["has_more"] is False
    assert data["pagination"]["total_count"] == 0


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
    data = resp.json()
    assert len(data["items"]) == 1
    assert data["pagination"]["total_count"] == 1


def test_list_signals_seeded(seeded_client):
    resp = seeded_client.get("/api/v1/signals")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["id"] == "sig-api001"
    assert data["pagination"]["total_count"] == 1


def test_signal_response_schema(seeded_client):
    """Verify response contains all SignalResponse fields."""
    resp = seeded_client.get("/api/v1/signals")
    response_data = resp.json()
    assert "items" in response_data
    assert "pagination" in response_data
    data = response_data["items"][0]
    expected_keys = {
        "id", "source_type", "source_adapter", "title", "content",
        "url", "author", "published_at", "fetched_at", "tags",
        "credibility", "metadata", "signal_role",
    }
    assert set(data.keys()) == expected_keys
    assert data["source_type"] == "forum"
    assert data["source_adapter"] == "test"
    assert data["signal_role"] == ""
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
            "signal_role": "solution",
            "metadata": {"key": "value"},
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["source_type"] == "registry"
    assert data["source_adapter"] == "npm"
    assert data["signal_role"] == "solution"
    assert data["author"] == "tester"
    assert data["tags"] == ["a", "b"]
    assert data["credibility"] == 0.9
    assert data["metadata"]["key"] == "value"
    assert data["metadata"]["signal_role"] == "solution"


def test_create_signal_uses_metadata_signal_role(client):
    resp = client.post(
        "/api/v1/signals",
        json={
            "title": "Metadata Role Signal",
            "content": "Content",
            "url": "https://example.com/metadata-role",
            "metadata": {"signal_role": "problem"},
        },
    )
    assert resp.status_code == 201
    assert resp.json()["signal_role"] == "problem"


def test_list_signals_filters_by_signal_role_and_source_type(client):
    client.post(
        "/api/v1/signals",
        json={
            "title": "Forum Problem",
            "content": "C1",
            "url": "https://example.com/forum-problem",
            "source_type": "forum",
            "source_adapter": "hackernews",
            "signal_role": "problem",
        },
    )
    client.post(
        "/api/v1/signals",
        json={
            "title": "Registry Problem",
            "content": "C2",
            "url": "https://example.com/registry-problem",
            "source_type": "registry",
            "source_adapter": "npm",
            "signal_role": "problem",
        },
    )
    client.post(
        "/api/v1/signals",
        json={
            "title": "Forum Solution",
            "content": "C3",
            "url": "https://example.com/forum-solution",
            "source_type": "forum",
            "source_adapter": "reddit",
            "signal_role": "solution",
        },
    )

    resp = client.get(
        "/api/v1/signals?source_type=forum&source_adapter=hackernews&signal_role=problem"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["pagination"]["total_count"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["title"] == "Forum Problem"
    assert data["items"][0]["source_type"] == "forum"
    assert data["items"][0]["source_adapter"] == "hackernews"
    assert data["items"][0]["signal_role"] == "problem"


def test_archive_signal_hides_from_list_but_returns_signal(seeded_client):
    resp = seeded_client.post("/api/v1/signals/sig-api001/archive")

    assert resp.status_code == 200
    assert resp.json()["id"] == "sig-api001"

    list_resp = seeded_client.get("/api/v1/signals")
    assert list_resp.status_code == 200
    data = list_resp.json()
    assert data["items"] == []
    assert data["pagination"]["total_count"] == 0


def test_restore_signal_returns_signal_to_list(seeded_client):
    seeded_client.post("/api/v1/signals/sig-api001/archive")

    resp = seeded_client.post("/api/v1/signals/sig-api001/restore")

    assert resp.status_code == 200
    assert resp.json()["id"] == "sig-api001"

    list_resp = seeded_client.get("/api/v1/signals")
    data = list_resp.json()
    assert [item["id"] for item in data["items"]] == ["sig-api001"]
    assert data["pagination"]["total_count"] == 1


def test_archive_signal_not_found_returns_404(seeded_client):
    resp = seeded_client.post("/api/v1/signals/sig-missing/archive")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Signal not found: sig-missing"


def test_restore_signal_not_found_returns_404(seeded_client):
    resp = seeded_client.post("/api/v1/signals/sig-missing/restore")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Signal not found: sig-missing"


# ── Insight endpoints ───────────────────────────────────────────────


def test_list_insights_empty(client):
    resp = client.get("/api/v1/insights")
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["pagination"]["has_more"] is False
    assert data["pagination"]["total_count"] == 0


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
    response_data = resp.json()
    assert len(response_data["items"]) == 1
    assert response_data["items"][0]["id"] == "ins-api001"
    assert response_data["items"][0]["title"] == "Test Insight"
    assert response_data["pagination"]["total_count"] == 1


def test_list_insights_filters(client):
    client.post(
        "/api/v1/insights",
        json={
            "category": "gap",
            "title": "Devtools Gap",
            "summary": "Summary",
            "domains": ["devtools", "ai"],
        },
    )
    client.post(
        "/api/v1/insights",
        json={
            "category": "trend",
            "title": "Healthcare Trend",
            "summary": "Summary",
            "domains": ["healthcare"],
        },
    )

    resp = client.get("/api/v1/insights?domain=devtools&category=gap")
    assert resp.status_code == 200
    response_data = resp.json()
    assert len(response_data["items"]) == 1
    assert response_data["items"][0]["title"] == "Devtools Gap"
    assert response_data["pagination"]["total_count"] == 1

    resp = client.get("/api/v1/insights?domain=devtools&category=trend")
    assert resp.status_code == 200
    response_data = resp.json()
    assert response_data["items"] == []
    assert response_data["pagination"]["total_count"] == 0


def test_insight_response_schema(seeded_client):
    """Verify response contains all InsightResponse fields."""
    resp = seeded_client.get("/api/v1/insights")
    response_data = resp.json()
    assert "items" in response_data
    assert "pagination" in response_data
    data = response_data["items"][0]
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


def test_get_insight_detail_resolves_evidence_signals(seeded_client):
    resp = seeded_client.get("/api/v1/insights/ins-api001")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "ins-api001"
    assert data["evidence"] == ["sig-api001"]
    assert [signal["id"] for signal in data["evidence_signals"]] == ["sig-api001"]
    assert data["evidence_signals"][0]["title"] == "Test Signal"
    assert data["missing_evidence_ids"] == []


def test_get_insight_detail_reports_missing_evidence_ids(client, db_path):
    store = Store(db_path=db_path, wal_mode=True)
    try:
        store.insert_signal(
            Signal(
                id="sig-existing",
                source_type=SignalSourceType.FORUM,
                source_adapter="test",
                title="Existing Signal",
                content="Still exists",
                url="https://example.com/existing",
            )
        )
        store.insert_insight(
            Insight(
                id="ins-missing-evidence",
                category=InsightCategory.GAP,
                title="Partial Evidence",
                summary="Some evidence was deleted.",
                evidence=["sig-existing", "sig-missing"],
                confidence=0.7,
            )
        )
    finally:
        store.close()

    resp = client.get("/api/v1/insights/ins-missing-evidence")
    assert resp.status_code == 200
    data = resp.json()
    assert [signal["id"] for signal in data["evidence_signals"]] == ["sig-existing"]
    assert data["missing_evidence_ids"] == ["sig-missing"]


def test_get_insight_not_found_returns_404(client):
    resp = client.get("/api/v1/insights/ins-does-not-exist")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Insight not found: ins-does-not-exist"


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
    data = resp.json()
    assert data["items"] == []
    assert data["pagination"]["has_more"] is False
    assert data["pagination"]["total_count"] == 0


def test_list_ideas_seeded(seeded_client):
    resp = seeded_client.get("/api/v1/ideas")
    assert resp.status_code == 200
    response_data = resp.json()
    assert len(response_data["items"]) == 1
    assert response_data["items"][0]["id"] == "bu-api001"
    assert response_data["items"][0]["score"] == 78.0
    assert response_data["pagination"]["total_count"] == 1


def test_list_ideas_filter_min_score(seeded_client):
    resp = seeded_client.get("/api/v1/ideas?min_score=90")
    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 0

    resp = seeded_client.get("/api/v1/ideas?min_score=50")
    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 1


def test_list_ideas_filter_status(multi_idea_client):
    """Filter ideas by status query parameter."""
    resp = multi_idea_client.get("/api/v1/ideas?status=draft")
    assert resp.status_code == 200
    response_data = resp.json()
    assert len(response_data["items"]) == 1
    assert response_data["items"][0]["status"] == "draft"

    resp = multi_idea_client.get("/api/v1/ideas?status=evaluated")
    assert resp.status_code == 200
    response_data = resp.json()
    assert len(response_data["items"]) == 1
    assert response_data["items"][0]["status"] == "evaluated"

    resp = multi_idea_client.get("/api/v1/ideas?status=nonexistent")
    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 0


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


def test_get_idea_evidence_chain(seeded_client):
    resp = seeded_client.get("/api/v1/ideas/bu-api001/evidence-chain")
    assert resp.status_code == 200
    data = resp.json()
    assert data["idea"]["id"] == "bu-api001"
    assert [insight["id"] for insight in data["insights"]] == ["ins-api001"]
    assert [signal["id"] for signal in data["signals"]] == ["sig-api001"]
    assert {
        (edge["source"], edge["target"], edge["type"])
        for edge in data["edges"]
    } == {
        ("bu-api001", "ins-api001", "inspired_by"),
        ("ins-api001", "sig-api001", "supported_by"),
        ("bu-api001", "sig-api001", "direct_evidence"),
    }


def test_get_idea_evidence_chain_not_found(client):
    resp = client.get("/api/v1/ideas/nonexistent/evidence-chain")
    assert resp.status_code == 404


def test_get_idea_domain_quality(seeded_client):
    resp = seeded_client.get("/api/v1/ideas/bu-api001/domain-quality")
    assert resp.status_code == 200
    data = resp.json()
    assert data[0]["overall_score"] == 76.0
    assert data[0]["passed_gate"] is True


def test_get_domain_quality_memory(seeded_client):
    resp = seeded_client.get("/api/v1/domains/testing/quality-memory")
    assert resp.status_code == 200
    data = resp.json()
    assert data[0]["pattern"] == "Test Idea: A test idea for the API"
    assert data[0]["outcome"] == "approved"


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


# ── Design brief endpoints ─────────────────────────────────────────


def test_list_design_briefs(seeded_client):
    resp = seeded_client.get("/api/v1/design-briefs")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["title"] == "Test Design Brief"
    assert data[0]["lead_idea_id"] == "bu-api001"
    assert data[0]["sources"][0]["idea_id"] == "bu-api001"


def test_get_design_brief(seeded_client):
    list_resp = seeded_client.get("/api/v1/design-briefs")
    brief_id = list_resp.json()[0]["id"]

    resp = seeded_client.get(f"/api/v1/design-briefs/{brief_id}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == brief_id
    assert data["mvp_scope"] == ["Export packet"]


def test_get_design_brief_blueprint(seeded_client):
    list_resp = seeded_client.get("/api/v1/design-briefs")
    brief_id = list_resp.json()[0]["id"]

    resp = seeded_client.get(f"/api/v1/design-briefs/{brief_id}/blueprint")

    assert resp.status_code == 200
    data = resp.json()
    assert data["schema_version"] == "max.blueprint.source_brief.v1"
    assert data["source"]["id"] == brief_id
    assert data["design_brief"]["title"] == "Test Design Brief"
    assert data["source_ideas"][0]["id"] == "bu-api001"


def test_get_design_brief_markdown(seeded_client):
    list_resp = seeded_client.get("/api/v1/design-briefs")
    brief_id = list_resp.json()[0]["id"]

    resp = seeded_client.get(f"/api/v1/design-briefs/{brief_id}/markdown")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/markdown")
    assert "# Test Design Brief" in resp.text
    assert "### MVP Scope" in resp.text
    assert "- Export packet" in resp.text
    assert "`bu-api001`" in resp.text


def test_get_design_brief_markdown_not_found(client):
    resp = client.get("/api/v1/design-briefs/dbf-missing/markdown")
    assert resp.status_code == 404


def test_get_design_brief_not_found(client):
    resp = client.get("/api/v1/design-briefs/dbf-missing")
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


# ── Health endpoint ──────────────────────────────────────────────────


def test_health_returns_healthy(client):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["database"] is True
    assert isinstance(data["version"], int)
    assert data["version"] > 0
    assert isinstance(data["uptime_seconds"], float)


# ── Pipeline run history endpoint ────────────────────────────────────


@pytest.fixture
def pipeline_runs_db(db_path):
    """DB pre-populated with pipeline run records."""
    store = Store(db_path=db_path, wal_mode=True)
    for i in range(1, 8):
        run_id = f"run-{i:03d}"
        store.insert_pipeline_run(run_id, {"signal_limit": 30})
        if i <= 5:
            store.update_pipeline_run(
                run_id,
                signals_fetched=i * 10,
                insights_generated=i * 2,
                ideas_generated=i,
                ideas_evaluated=i,
            )
    store.close()
    return db_path


@pytest.fixture
def pipeline_runs_client(pipeline_runs_db):
    from max.server.dependencies import get_store

    app = create_app()

    def override():
        store = Store(db_path=pipeline_runs_db, wal_mode=True)
        try:
            yield store
        finally:
            store.close()

    app.dependency_overrides[get_store] = override
    return TestClient(app)


def test_list_pipeline_runs(pipeline_runs_client):
    resp = pipeline_runs_client.get("/api/v1/pipeline/runs")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 7
    for run in data:
        assert "id" in run
        assert "started_at" in run
        assert "status" in run


def test_list_pipeline_runs_limit(pipeline_runs_client):
    resp = pipeline_runs_client.get("/api/v1/pipeline/runs?limit=5")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 5


def test_list_pipeline_runs_empty(client):
    resp = client.get("/api/v1/pipeline/runs")
    assert resp.status_code == 200
    assert resp.json() == []


def _api_mock_profile(name: str, domain_name: str):
    from max.profiles.schema import DomainContext, PipelineProfile

    return PipelineProfile(
        name=name,
        domain=DomainContext(
            name=domain_name,
            description=f"{domain_name} domain",
            categories=["cli_tool"],
            target_user_types=["developers"],
        ),
    )


def _api_mock_pipeline_result(
    *,
    signals_fetched: int,
    signals_new: int,
    insights_generated: int,
    ideas_generated: int,
    ideas_evaluated: int,
    token_usage: dict[str, int] | None = None,
):
    from max.pipeline.runner import PipelineResult

    return PipelineResult(
        signals_fetched=signals_fetched,
        signals_new=signals_new,
        insights_generated=insights_generated,
        ideas_generated=ideas_generated,
        ideas_evaluated=ideas_evaluated,
        avg_insight_confidence=0.8,
        avg_idea_score=70.0,
        token_usage=token_usage or {},
        top_ideas=[],
    )


def test_pipeline_run_all_respects_focus(client, tmp_path, monkeypatch):
    from max.focus import save_focus_domains

    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    monkeypatch.setattr("max.focus.get_profiles_dir", lambda: profiles_dir)
    save_focus_domains(["developer-tools"])

    profiles = {
        "devtools": "developer-tools",
        "healthcare": "healthcare",
    }

    with (
        patch("max.profiles.loader.list_profiles", return_value=list(profiles)),
        patch(
            "max.profiles.loader.load_profile",
            side_effect=lambda name: _api_mock_profile(name, profiles[name]),
        ),
        patch(
            "max.pipeline.runner.run_pipeline",
            return_value=_api_mock_pipeline_result(
                signals_fetched=2,
                signals_new=1,
                insights_generated=1,
                ideas_generated=1,
                ideas_evaluated=1,
            ),
        ) as mock_run,
    ):
        resp = client.post("/api/v1/pipeline/run", json={"profile": "all"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["profile"] == "all"
    assert data["profiles_run"] == 1
    assert data["focus_domains"] == ["developer-tools"]
    assert data["skipped_profiles"] == ["healthcare"]
    assert data["profiles"][0]["profile_name"] == "devtools"
    assert data["profiles"][0]["domain"] == "developer-tools"
    assert data["totals"]["signals_fetched"] == 2
    assert mock_run.call_count == 1


def test_pipeline_run_all_include_all_bypasses_focus_and_aggregates(
    client, tmp_path, monkeypatch
):
    from max.focus import save_focus_domains

    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    monkeypatch.setattr("max.focus.get_profiles_dir", lambda: profiles_dir)
    save_focus_domains(["developer-tools"])

    profiles = {
        "devtools": "developer-tools",
        "healthcare": "healthcare",
    }
    results = [
        _api_mock_pipeline_result(
            signals_fetched=2,
            signals_new=1,
            insights_generated=1,
            ideas_generated=1,
            ideas_evaluated=1,
            token_usage={"input": 10},
        ),
        _api_mock_pipeline_result(
            signals_fetched=3,
            signals_new=2,
            insights_generated=2,
            ideas_generated=2,
            ideas_evaluated=2,
            token_usage={"input": 20, "output": 5},
        ),
    ]

    with (
        patch("max.profiles.loader.list_profiles", return_value=list(profiles)),
        patch(
            "max.profiles.loader.load_profile",
            side_effect=lambda name: _api_mock_profile(name, profiles[name]),
        ),
        patch("max.pipeline.runner.run_pipeline", side_effect=results) as mock_run,
    ):
        resp = client.post(
            "/api/v1/pipeline/run",
            json={"profile": "all", "include_all": True},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["include_all"] is True
    assert data["focus_domains"] is None
    assert data["skipped_profiles"] == []
    assert data["profiles_run"] == 2
    assert data["totals"]["signals_fetched"] == 5
    assert data["totals"]["signals_new"] == 3
    assert data["totals"]["ideas_evaluated"] == 3
    assert data["totals"]["token_usage"] == {"input": 30, "output": 5}
    assert [p["profile_name"] for p in data["profiles"]] == ["devtools", "healthcare"]
    assert mock_run.call_count == 2


def test_pipeline_dry_run_loads_profile_applies_overrides_and_returns_report(client):
    from max.types.pipeline import DryRunReport, StageSummary

    profile = _api_mock_profile("devtools", "developer-tools")
    profile.signal_limit = 99
    report = DryRunReport(
        stages=[
            StageSummary(
                name="fetch",
                would_process=12,
                estimated_llm_calls=0,
                skipped=False,
                reason="",
            )
        ],
        estimated_total_llm_calls=0,
        estimated_token_budget=0,
    )

    with (
        patch("max.profiles.loader.load_profile", return_value=profile) as mock_load,
        patch("max.pipeline.runner.run_pipeline", return_value=report) as mock_run,
    ):
        resp = client.post(
            "/api/v1/pipeline/dry-run",
            json={"profile": "devtools", "signal_limit": 12, "stages": ["fetch"]},
        )

    assert resp.status_code == 200
    assert resp.json() == {
        "stages": [
            {
                "name": "fetch",
                "would_process": 12,
                "estimated_llm_calls": 0,
                "skipped": False,
                "reason": "",
            }
        ],
        "estimated_total_llm_calls": 0,
        "estimated_token_budget": 0,
    }
    mock_load.assert_called_once_with("devtools")
    _, kwargs = mock_run.call_args
    assert kwargs["dry_run"] is True
    assert kwargs["stages"] == ["fetch"]
    assert kwargs["profile"].signal_limit == 12
    assert profile.signal_limit == 99


def test_pipeline_dry_run_returns_404_for_unknown_profile(client):
    with patch("max.profiles.loader.load_profile", side_effect=FileNotFoundError("missing")):
        resp = client.post("/api/v1/pipeline/dry-run", json={"profile": "missing"})

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Profile not found: missing"


def test_pipeline_dry_run_returns_400_for_invalid_stages(client):
    profile = _api_mock_profile("devtools", "developer-tools")

    with (
        patch("max.profiles.loader.get_default_profile", return_value=profile),
        patch("max.pipeline.runner.run_pipeline", side_effect=ValueError("Unknown stages: nope")),
    ):
        resp = client.post("/api/v1/pipeline/dry-run", json={"stages": ["nope"]})

    assert resp.status_code == 400
    assert resp.json()["detail"] == "Unknown stages: nope"


def test_pipeline_post_run_invokes_runner(client):
    from max.pipeline.runner import PostPipelineResult

    result = PostPipelineResult(
        duplicates_found=99,
        duplicates_marked=2,
        synthesis_clusters=3,
        ideas_synthesized=4,
        source_ideas_merged=5,
        prior_art_checked=6,
        prior_art_strong=7,
        prior_art_weak=8,
        prior_art_clear=9,
        triage_auto_approved=10,
        triage_auto_rejected=11,
        triage_pending_review=12,
    )

    with patch("max.pipeline.runner.run_post_pipeline", return_value=result) as mock_run:
        resp = client.post("/api/v1/pipeline/post-run", json={})

    assert resp.status_code == 200
    assert resp.json() == {
        "duplicates_marked": 2,
        "ideas_synthesized": 4,
        "source_ideas_merged": 5,
        "synthesis_clusters": 3,
        "prior_art_checked": 6,
        "prior_art_strong": 7,
        "prior_art_weak": 8,
        "prior_art_clear": 9,
        "triage_auto_approved": 10,
        "triage_auto_rejected": 11,
        "triage_pending_review": 12,
    }
    mock_run.assert_called_once_with(domain=None)


def test_pipeline_post_run_passes_optional_domain(client):
    from max.pipeline.runner import PostPipelineResult

    with patch(
        "max.pipeline.runner.run_post_pipeline",
        return_value=PostPipelineResult(),
    ) as mock_run:
        resp = client.post("/api/v1/pipeline/post-run", json={"domain": "fintech"})

    assert resp.status_code == 200
    mock_run.assert_called_once_with(domain="fintech")
