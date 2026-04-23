"""Tests for the REST API endpoints."""

from __future__ import annotations

import csv
import json
from datetime import datetime
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from max.analysis.export import IDEA_EXPORT_FIELDS
from max.analysis.prior_art import PriorArtMatch, PriorArtResult
from max.evaluation.weights import WEIGHT_PROFILES, get_weights
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
        domain="testing",
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
    store.insert_idea_memory(
        unit_id="bu-api001",
        domain="testing",
        outcome="approved",
        pattern="Test Idea: A test idea for the API",
        rejection_tags=[],
        score=76.0,
        evidence_rationale="seeded",
    )
    store.insert_prior_art_match(
        "bu-api001",
        {
            "source": "github",
            "title": "Existing Test Idea",
            "url": "https://github.com/example/existing-test-idea",
            "description": "A persisted match for API tests.",
            "relevance_score": 0.88,
            "match_signals": {"stars": 42},
            "search_query": "test idea",
        },
    )
    store.update_prior_art_status("bu-api001", "weak_match")
    store.close()
    return db_path


def _threshold_unit(unit_id: str, domain: str) -> BuildableUnit:
    return BuildableUnit(
        id=unit_id,
        title=f"Threshold Idea {unit_id}",
        one_liner="A threshold test idea",
        category=BuildableCategory.APPLICATION,
        problem="Problem",
        solution="Solution",
        value_proposition="Value",
        domain=domain,
    )


def _threshold_evaluation(unit_id: str, score: float) -> UtilityEvaluation:
    dim = DimensionScore(value=7.0, confidence=0.7, reasoning="test")
    return UtilityEvaluation(
        buildable_unit_id=unit_id,
        pain_severity=dim,
        addressable_scale=dim,
        build_effort=dim,
        composability=dim,
        competitive_density=dim,
        timing_fit=dim,
        compounding_value=dim,
        overall_score=score,
        recommendation="yes" if score >= 68 else "no",
    )


def _seed_threshold_feedback(
    db_path: str,
    unit_id: str,
    domain: str,
    score: float,
    outcome: str,
) -> None:
    store = Store(db_path=db_path, wal_mode=True)
    try:
        store.insert_buildable_unit(_threshold_unit(unit_id, domain))
        store.insert_evaluation(_threshold_evaluation(unit_id, score))
        store.insert_feedback(unit_id, outcome)
    finally:
        store.close()


def test_review_thresholds_returns_recommendations(client, db_path) -> None:
    for idx, score in enumerate([70.0, 80.0, 90.0], 1):
        _seed_threshold_feedback(db_path, f"bu-api-ap-{idx}", "devtools", score, "approved")
    for idx, score in enumerate([30.0, 40.0, 50.0], 1):
        _seed_threshold_feedback(db_path, f"bu-api-rj-{idx}", "devtools", score, "rejected")

    response = client.get("/api/v1/review-thresholds?min_samples=4")

    assert response.status_code == 200
    payload = response.json()
    assert payload["min_samples"] == 4
    assert payload["default_approve_threshold"] == 68.0
    assert payload["default_reject_threshold"] == 50.0
    assert payload["recommendations"] == [
        {
            "domain": "devtools",
            "approve_threshold": 75.0,
            "reject_threshold": 45.0,
            "sample_count": 6,
            "approved_count": 3,
            "rejected_count": 3,
            "sufficient_samples": True,
            "fallback_used": False,
            "reason": "computed from approved and rejected feedback",
        }
    ]


def test_review_thresholds_domain_filter_and_insufficient_samples(client, db_path) -> None:
    _seed_threshold_feedback(db_path, "bu-api-one", "legaltech", 88.0, "approved")
    _seed_threshold_feedback(db_path, "bu-api-other", "devtools", 42.0, "rejected")

    response = client.get("/api/v1/review-thresholds?domain=legaltech&min_samples=2")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["recommendations"]) == 1
    rec = payload["recommendations"][0]
    assert rec["domain"] == "legaltech"
    assert rec["sample_count"] == 1
    assert rec["sufficient_samples"] is False
    assert rec["approve_threshold"] == 68.0
    assert rec["reject_threshold"] == 50.0


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


def _seed_api_pipeline_run(
    db_path: str,
    run_id: str,
    *,
    signals_fetched: int,
    ideas_generated: int,
    adapter_metrics: dict,
) -> None:
    store = Store(db_path=db_path, wal_mode=True)
    try:
        store.insert_pipeline_run(run_id, {"model": "gpt-4o-mini"})
        store.update_pipeline_run(
            run_id,
            signals_fetched=signals_fetched,
            signals_new=signals_fetched,
            insights_generated=1,
            ideas_generated=ideas_generated,
            ideas_evaluated=ideas_generated,
            token_usage={"input": 100, "output": 50, "estimated_cost_usd": 0.01},
            adapter_metrics=adapter_metrics,
            status="completed",
        )
    finally:
        store.close()


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


def _mock_evaluation_output(recommendation: str = "yes"):
    mock_dim = type("Dim", (), {"value": 8.0, "confidence": 0.8, "reasoning": "test"})()
    return type(
        "EvalOut",
        (),
        {
            "pain_severity": mock_dim,
            "addressable_scale": mock_dim,
            "build_effort": mock_dim,
            "composability": mock_dim,
            "competitive_density": mock_dim,
            "timing_fit": mock_dim,
            "compounding_value": mock_dim,
            "strengths": ["Strong"],
            "weaknesses": ["Weak"],
            "recommendation": recommendation,
        },
    )()


def _api_dimension_score(value: float) -> DimensionScore:
    return DimensionScore(value=value, confidence=0.7, reasoning="test")


def _api_evaluation(unit_id: str, score: float, recommendation: str = "yes") -> UtilityEvaluation:
    return UtilityEvaluation(
        buildable_unit_id=unit_id,
        pain_severity=_api_dimension_score(8.0),
        addressable_scale=_api_dimension_score(7.0),
        build_effort=_api_dimension_score(7.5),
        composability=_api_dimension_score(8.5),
        competitive_density=_api_dimension_score(9.0),
        timing_fit=_api_dimension_score(8.0),
        compounding_value=_api_dimension_score(7.0),
        overall_score=score,
        strengths=["Good"],
        weaknesses=["Limited"],
        recommendation=recommendation,
        weights_used={"pain_severity": 0.20},
    )


def _api_buildable_unit(unit_id: str, *, status: str, domain: str) -> BuildableUnit:
    return BuildableUnit(
        id=unit_id,
        title=f"Export {unit_id}",
        one_liner=f"One liner for {unit_id}",
        category=BuildableCategory.CLI_TOOL,
        ideation_mode=IdeationMode.DIRECT,
        problem="Problem",
        solution="Solution",
        value_proposition="Value",
        status=status,
        domain=domain,
        quality_score=7.0,
        novelty_score=6.0,
        usefulness_score=8.0,
        rejection_tags=["too_broad"] if status == "rejected" else [],
        inspiring_insights=["ins-export"],
        evidence_signals=["sig-export"],
        source_idea_ids=["bu-source"],
    )


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


def test_validate_profiles_returns_structured_results(client):
    from max.profiles.validation import ProfileFileValidationResult, ProfileValidationIssue

    validation_result = ProfileFileValidationResult.from_issues(
        "devtools",
        Path("profiles/devtools.yaml"),
        [
            ProfileValidationIssue(
                severity="warning",
                code="duplicate_category",
                message="Duplicate category 'cli_tool'",
                path="domain.categories",
            )
        ],
    )

    with patch("max.profiles.loader.validate_profile_files", return_value=[validation_result]):
        resp = client.get("/api/v1/profiles/validate?profile=devtools")

    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["profile"] == "devtools"
    assert data["results"][0]["warnings"][0] == {
        "severity": "warning",
        "code": "duplicate_category",
        "message": "Duplicate category 'cli_tool'",
        "path": "domain.categories",
    }


def test_get_profile_coverage_gaps_returns_uncovered_terms(client, db_path):
    from max.profiles.schema import DomainContext, PipelineProfile, SourceConfig

    profile = PipelineProfile(
        name="coverage",
        domain=DomainContext(
            name="testing",
            description="testing domain",
            categories=["mcp", "workflow automation"],
            target_user_types=["developers"],
        ),
        sources=[
            SourceConfig(adapter="hackernews", watchlist=["mcp", "agent testing"]),
            SourceConfig(adapter="reddit", params={"queries": ["agent testing"]}),
        ],
    )
    store = Store(db_path=db_path, wal_mode=True)
    store.insert_signal(
        Signal(
            id="sig-coverage-api",
            source_type=SignalSourceType.FORUM,
            source_adapter="hackernews",
            title="MCP coverage exists",
            content="A stored active signal",
            url="https://example.com/coverage-api",
            tags=[],
        )
    )
    store.close()

    with patch("max.profiles.loader.load_profile", return_value=profile):
        resp = client.get("/api/v1/profiles/coverage/coverage-gaps")

    assert resp.status_code == 200
    data = resp.json()
    assert data["profile_name"] == "coverage"
    assert data["domain"] == "testing"
    assert data["enabled_adapters"] == ["hackernews", "reddit"]

    by_term = {term["term"]: term for term in data["terms"]}
    assert "mcp" not in by_term
    assert by_term["agent testing"]["adapter_counts"] == {"hackernews": 0, "reddit": 0}
    assert by_term["agent testing"]["suggested_source_adapters"] == ["hackernews", "reddit"]
    assert by_term["workflow automation"]["enabled_adapters"] == ["hackernews", "reddit"]


def test_get_profile_coverage_gaps_returns_404_for_unknown_profile(client):
    with patch("max.profiles.loader.load_profile", side_effect=FileNotFoundError("missing")):
        resp = client.get("/api/v1/profiles/missing/coverage-gaps")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Profile not found: missing"


def test_get_profile_source_recommendations_response_shape(client):
    from max.profiles.schema import DomainContext, PipelineProfile, SourceConfig

    profile = PipelineProfile(
        name="recommendations",
        domain=DomainContext(
            name="testing",
            description="testing domain",
            categories=["application"],
            target_user_types=["developers"],
        ),
        sources=[SourceConfig(adapter="hackernews", enabled=True, weight=1.0)],
    )

    with (
        patch("max.profiles.loader.load_profile", return_value=profile),
        patch(
            "max.analysis.profile_source_recommendations.list_adapters",
            return_value=["hackernews"],
        ),
    ):
        resp = client.get("/api/v1/profiles/recommendations/source-recommendations")

    assert resp.status_code == 200
    data = resp.json()
    assert data["profile_name"] == "recommendations"
    assert data["domain"] == "testing"
    assert data["max_age_days"] == 30
    assert len(data["recommendations"]) == 1
    rec = data["recommendations"][0]
    assert rec["adapter"] == "hackernews"
    assert rec["action"] == "keep"
    assert rec["current_weight"] == 1.0
    assert rec["suggested_weight"] == 1.0
    assert rec["evidence"]["registered"] is True
    assert set(rec) == {
        "adapter",
        "action",
        "severity",
        "enabled",
        "registered",
        "configured",
        "current_weight",
        "suggested_weight",
        "reasons",
        "evidence",
    }


# ── Evaluation weight endpoints ─────────────────────────────────────


def test_list_evaluation_weight_profiles_returns_all_built_ins(client):
    resp = client.get("/api/v1/evaluation/weights")

    assert resp.status_code == 200
    data = resp.json()
    assert [profile["name"] for profile in data] == list(WEIGHT_PROFILES)
    for profile in data:
        assert profile["weights"] == get_weights(profile["name"])
        assert profile["adapted"] is False
        assert profile["adapted_weights"] is None


def test_get_evaluation_weight_profile_matches_static_weights(client):
    resp = client.get("/api/v1/evaluation/weights/agent_first")

    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "agent_first"
    assert data["weights"] == get_weights("agent_first")
    assert data["adapted"] is False
    assert data["adapted_weights"] is None


def test_get_evaluation_weight_profile_returns_adapted_weights_when_available(client):
    adapted_weights = {
        "pain_severity": 0.3,
        "addressable_scale": 0.1,
        "build_effort": 0.1,
        "composability": 0.2,
        "competitive_density": 0.05,
        "timing_fit": 0.1,
        "compounding_value": 0.15,
    }

    with patch("max.server.api.get_adapted_weights", return_value=(adapted_weights, True)):
        resp = client.get("/api/v1/evaluation/weights/default")

    assert resp.status_code == 200
    data = resp.json()
    assert data["weights"] == get_weights("default")
    assert data["adapted"] is True
    assert data["adapted_weights"] == adapted_weights


def test_get_evaluation_weight_profile_returns_404_for_unknown_profile(client):
    resp = client.get("/api/v1/evaluation/weights/unknown_profile_xyz")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Evaluation weight profile not found: unknown_profile_xyz"


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
    assert data["status"] == "created"


def test_create_signal_duplicate_returns_existing_signal(client):
    first = client.post(
        "/api/v1/signals",
        json={
            "title": "Original Signal",
            "content": "Signal content",
            "url": "https://example.com/duplicate-api",
        },
    )
    second = client.post(
        "/api/v1/signals",
        json={
            "title": "Duplicate Signal",
            "content": "Different content",
            "url": "https://example.com/duplicate-api",
        },
    )

    assert first.status_code == 201
    assert second.status_code == 200
    data = second.json()
    assert data["status"] == "duplicate"
    assert data["id"] == first.json()["id"]
    assert data["title"] == "Original Signal"


def test_import_signals_reports_inserted_duplicate_and_invalid_rows(client):
    resp = client.post(
        "/api/v1/signals/import",
        json={
            "source_adapter": "manual",
            "source_type": "article",
            "credibility": 0.8,
            "tags": ["batch"],
            "rows": [
                {
                    "title": "Imported Signal",
                    "content": "Imported content",
                    "url": "https://example.com/imported-signal",
                    "tags": "row,batch",
                    "metadata": "{\"channel\": \"api\"}",
                    "signal_role": "problem",
                },
                {
                    "title": "Duplicate Imported Signal",
                    "content": "Different content",
                    "url": "https://example.com/imported-signal",
                },
                {
                    "title": "Invalid Imported Signal",
                    "url": "https://example.com/invalid-imported-signal",
                },
            ],
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["inserted_count"] == 1
    assert data["duplicate_count"] == 1
    assert data["error_count"] == 1

    inserted = data["results"][0]
    duplicate = data["results"][1]
    invalid = data["results"][2]
    assert inserted["index"] == 0
    assert inserted["signal_id"].startswith("sig-")
    assert inserted["duplicate_id"] is None
    assert inserted["error"] is None
    assert duplicate == {
        "index": 1,
        "signal_id": None,
        "duplicate_id": inserted["signal_id"],
        "error": None,
    }
    assert invalid["index"] == 2
    assert invalid["signal_id"] is None
    assert invalid["duplicate_id"] is None
    assert "missing required field(s): content" in invalid["error"]

    list_resp = client.get("/api/v1/signals")
    item = list_resp.json()["items"][0]
    assert item["source_adapter"] == "manual"
    assert item["source_type"] == "article"
    assert item["credibility"] == 0.8
    assert item["tags"] == ["batch", "row"]
    assert item["metadata"] == {"channel": "api", "signal_role": "problem"}


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


def test_insight_trends_response_ordering_and_limit(client):
    for i, confidence in enumerate([0.6, 0.7, 0.8], start=1):
        client.post(
            "/api/v1/insights",
            json={
                "category": "gap",
                "title": f"Devtools Gap {i}",
                "summary": "Summary",
                "evidence": [f"sig-dev-{i}", "sig-shared"],
                "confidence": confidence,
                "domains": ["devtools"],
                "time_horizon": "near_term",
            },
        )
    for i, confidence in enumerate([0.95, 0.9], start=1):
        client.post(
            "/api/v1/insights",
            json={
                "category": "trend",
                "title": f"Healthcare Trend {i}",
                "summary": "Summary",
                "evidence": [f"sig-health-{i}"],
                "confidence": confidence,
                "domains": ["healthcare"],
                "time_horizon": "near_term",
            },
        )
    client.post(
        "/api/v1/insights",
        json={
            "category": "gap",
            "title": "AI Gap",
            "summary": "Summary",
            "domains": ["ai"],
        },
    )

    resp = client.get("/api/v1/trends/insights?limit=2")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_insights"] == 6
    assert data["trend_count"] == 2
    assert [(trend["category"], trend["domain"], trend["count"]) for trend in data["trends"]] == [
        ("gap", "devtools", 3),
        ("trend", "healthcare", 2),
    ]
    assert data["trends"][0]["average_confidence"] == pytest.approx(0.7)
    assert data["trends"][0]["top_evidence_signal_ids"][0] == "sig-shared"


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


def test_export_ideas_jsonl_response_shape(seeded_client):
    resp = seeded_client.get("/api/v1/exports/ideas")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    assert resp.headers["content-disposition"] == 'attachment; filename="ideas-export.jsonl"'

    lines = resp.text.splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert list(row.keys()) == list(IDEA_EXPORT_FIELDS)
    assert row["id"] == "bu-api001"
    assert row["evaluation_score"] == 78.0
    assert row["recommendation"] == "yes"
    assert row["inspiring_insight_ids"] == ["ins-api001"]
    assert row["evidence_signal_ids"] == ["sig-api001"]


def test_export_ideas_filters_status_domain_score_archived_and_limit(client, db_path):
    store = Store(db_path=db_path, wal_mode=True)
    try:
        rows = [
            ("bu-export-high", "evaluated", "ai", 91.0),
            ("bu-export-low", "evaluated", "ai", 60.0),
            ("bu-export-other-domain", "evaluated", "ops", 95.0),
            ("bu-export-draft", "draft", "ai", None),
            ("bu-export-archived", "archived", "ai", 99.0),
        ]
        for unit_id, status, domain, score in rows:
            store.insert_buildable_unit(_api_buildable_unit(unit_id, status=status, domain=domain))
            if score is not None:
                store.insert_evaluation(_api_evaluation(unit_id, score))
    finally:
        store.close()

    resp = client.get(
        "/api/v1/exports/ideas?fmt=jsonl&status=evaluated&domain=ai&min_score=80&limit=10"
    )
    assert resp.status_code == 200
    records = [json.loads(line) for line in resp.text.splitlines()]
    assert [row["id"] for row in records] == ["bu-export-high"]

    resp = client.get("/api/v1/exports/ideas?fmt=jsonl&domain=ai&min_score=90&limit=10")
    assert resp.status_code == 200
    ids = {json.loads(line)["id"] for line in resp.text.splitlines()}
    assert ids == {"bu-export-high"}

    resp = client.get(
        "/api/v1/exports/ideas?fmt=jsonl&domain=ai&min_score=90&include_archived=true&limit=10"
    )
    assert resp.status_code == 200
    ids = {json.loads(line)["id"] for line in resp.text.splitlines()}
    assert ids == {"bu-export-high", "bu-export-archived"}

    resp = client.get("/api/v1/exports/ideas?fmt=jsonl&include_archived=true&limit=1")
    assert resp.status_code == 200
    assert len(resp.text.splitlines()) == 1


def test_export_ideas_csv_header_output(seeded_client):
    resp = seeded_client.get("/api/v1/exports/ideas?fmt=csv")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert resp.headers["content-disposition"] == 'attachment; filename="ideas-export.csv"'

    reader = csv.DictReader(StringIO(resp.text))
    assert reader.fieldnames == list(IDEA_EXPORT_FIELDS)
    rows = list(reader)
    assert rows[0]["id"] == "bu-api001"
    assert rows[0]["evaluation_score"] == "78.0"
    assert json.loads(rows[0]["inspiring_insight_ids"]) == ["ins-api001"]


def test_export_ideas_invalid_fmt_returns_validation_error(client):
    resp = client.get("/api/v1/exports/ideas?fmt=xml")
    assert resp.status_code == 422


def test_get_review_queue_returns_unreviewed_evaluated_ideas(client, db_path):
    store = Store(db_path=db_path, wal_mode=True)

    def _score(value: float) -> DimensionScore:
        return DimensionScore(value=value, confidence=0.7, reasoning="seed")

    def _unit(unit_id: str, title: str, *, domain: str, status: str = "evaluated") -> BuildableUnit:
        return BuildableUnit(
            id=unit_id,
            title=title,
            one_liner="Queue candidate",
            category=BuildableCategory.CLI_TOOL,
            ideation_mode=IdeationMode.DIRECT,
            problem="Review queue needs candidates",
            solution="Return candidates from API",
            value_proposition="Faster review",
            status=status,
            domain=domain,
        )

    def _evaluation(unit_id: str, score: float) -> UtilityEvaluation:
        return UtilityEvaluation(
            buildable_unit_id=unit_id,
            pain_severity=_score(8.0),
            addressable_scale=_score(7.0),
            build_effort=_score(6.0),
            composability=_score(7.0),
            competitive_density=_score(8.0),
            timing_fit=_score(7.0),
            compounding_value=_score(6.0),
            overall_score=score,
            strengths=["clear pain"],
            weaknesses=["needs validation"],
            recommendation="yes",
            weights_used={"pain_severity": 0.2},
        )

    try:
        seeds = [
            (_unit("bu-queue-high", "High Queue", domain="ai"), 88.0, None),
            (_unit("bu-queue-low", "Low Queue", domain="ai"), 65.0, None),
            (_unit("bu-queue-reviewed", "Reviewed Queue", domain="ai"), 91.0, "rejected"),
            (_unit("bu-queue-other", "Other Queue", domain="devtools"), 93.0, None),
            (_unit("bu-queue-draft", "Draft Queue", domain="ai", status="draft"), 99.0, None),
        ]
        for unit, score, outcome in seeds:
            store.insert_buildable_unit(unit)
            store.insert_evaluation(_evaluation(unit.id, score))
            if outcome:
                store.insert_feedback(unit.id, outcome, "already reviewed")
        store.insert_idea_critique(
            "bu-queue-high",
            {
                "buyer_clarity": 8.0,
                "quality_score": 7.5,
                "reasoning": "Clear buyer.",
                "rejection_tags": [],
            },
        )
    finally:
        store.close()

    resp = client.get("/api/v1/review-queue?domain=ai&min_score=70&limit=10")

    assert resp.status_code == 200
    data = resp.json()
    assert [item["id"] for item in data] == ["bu-queue-high"]
    assert data[0]["score"] == 88.0
    assert data[0]["review_state"] == "pending_review"
    assert data[0]["feedback_outcome"] is None
    assert data[0]["evaluation"] == {
        "overall_score": 88.0,
        "rank": None,
        "recommendation": "yes",
        "strengths": ["clear pain"],
        "weaknesses": ["needs validation"],
    }
    assert data[0]["latest_critique"]["dimensions"]["buyer_clarity"] == 8.0
    assert data[0]["latest_critique"]["reasoning"] == "Clear buyer."


def test_get_idea_status_summary(client, db_path):
    store = Store(db_path=db_path, wal_mode=True)

    def _unit(unit_id: str, status: str, domain: str) -> BuildableUnit:
        return BuildableUnit(
            id=unit_id,
            title=f"Idea {unit_id}",
            one_liner="A summarized idea",
            category=BuildableCategory.CLI_TOOL,
            ideation_mode=IdeationMode.DIRECT,
            problem="Problem",
            solution="Solution",
            value_proposition="Value",
            status=status,
            domain=domain,
        )

    store.insert_buildable_unit(_unit("bu-summary-1", "evaluated", "ai"))
    store.insert_buildable_unit(_unit("bu-summary-2", "approved", "ai"))
    store.insert_buildable_unit(_unit("bu-summary-3", "duplicate", "devtools"))

    def _score(val):
        return DimensionScore(value=val, confidence=0.7, reasoning="test")

    evaluation = UtilityEvaluation(
        buildable_unit_id="bu-summary-1",
        pain_severity=_score(8.0),
        addressable_scale=_score(7.0),
        build_effort=_score(6.0),
        composability=_score(7.0),
        competitive_density=_score(8.0),
        timing_fit=_score(7.0),
        compounding_value=_score(6.0),
        overall_score=74.0,
        recommendation="yes",
        weights_used={"pain_severity": 0.20},
    )
    store.insert_evaluation(evaluation)
    store.close()

    resp = client.get("/api/v1/ideas/status-summary")
    assert resp.status_code == 200
    data = resp.json()

    assert data["total"] == 3
    assert data["totals"] == {
        "pending_review": 1,
        "approved": 1,
        "rejected": 0,
        "published": 0,
        "archived": 0,
        "duplicate": 1,
        "synthesized": 0,
    }
    assert {"status": "pending_review", "count": 1} in data["by_status"]
    assert {row["recommendation"] for row in data["by_recommendation"]} == {"yes"}
    assert any(
        row == {
            "status": "pending_review",
            "domain": "ai",
            "recommendation": "yes",
            "count": 1,
        }
        for row in data["groups"]
    )


def test_get_idea_score_distribution(client, db_path):
    store = Store(db_path=db_path, wal_mode=True)

    def _unit(unit_id: str, status: str, domain: str) -> BuildableUnit:
        return BuildableUnit(
            id=unit_id,
            title=f"Idea {unit_id}",
            one_liner="A distributed idea",
            category=BuildableCategory.CLI_TOOL,
            ideation_mode=IdeationMode.DIRECT,
            problem="Problem",
            solution="Solution",
            value_proposition="Value",
            status=status,
            domain=domain,
        )

    def _score(val):
        return DimensionScore(value=val, confidence=0.7, reasoning="test")

    def _evaluation(unit_id: str, score: float, recommendation: str) -> UtilityEvaluation:
        return UtilityEvaluation(
            buildable_unit_id=unit_id,
            pain_severity=_score(8.0),
            addressable_scale=_score(7.0),
            build_effort=_score(6.0),
            composability=_score(7.0),
            competitive_density=_score(8.0),
            timing_fit=_score(7.0),
            compounding_value=_score(6.0),
            overall_score=score,
            recommendation=recommendation,
            weights_used={"pain_severity": 0.20},
        )

    seeds = [
        (_unit("bu-score-1", "evaluated", "ai"), 71.0, "yes"),
        (_unit("bu-score-2", "evaluated", "ai"), 78.0, "maybe"),
        (_unit("bu-score-3", "approved", "ai"), 92.0, "yes"),
        (_unit("bu-score-4", "evaluated", "devtools"), 65.0, "no"),
    ]
    for unit, score, recommendation in seeds:
        store.insert_buildable_unit(unit)
        store.insert_evaluation(_evaluation(unit.id, score, recommendation))
    store.insert_buildable_unit(_unit("bu-score-unevaluated", "draft", "ai"))
    store.close()

    resp = client.get("/api/v1/ideas/score-distribution?bucket_size=20")

    assert resp.status_code == 200
    data = resp.json()
    assert data["bucket_size"] == 20
    assert data["evaluated_count"] == 4
    assert data["unevaluated_count"] == 1
    buckets = {row["min_score"]: row for row in data["buckets"]}
    assert buckets[60.0]["count"] == 3
    assert buckets[60.0]["average_score"] == pytest.approx((71.0 + 78.0 + 65.0) / 3)
    assert buckets[60.0]["by_recommendation"] == {"yes": 1, "maybe": 1, "no": 1}
    assert buckets[60.0]["by_status"] == {"evaluated": 3}
    assert buckets[80.0]["count"] == 1
    assert buckets[80.0]["by_recommendation"] == {"yes": 1}
    assert buckets[80.0]["by_status"] == {"approved": 1}


def test_get_idea_score_distribution_filters(client, db_path):
    store = Store(db_path=db_path, wal_mode=True)

    def _unit(unit_id: str, status: str, domain: str) -> BuildableUnit:
        return BuildableUnit(
            id=unit_id,
            title=f"Idea {unit_id}",
            one_liner="A filtered distribution idea",
            category=BuildableCategory.CLI_TOOL,
            ideation_mode=IdeationMode.DIRECT,
            problem="Problem",
            solution="Solution",
            value_proposition="Value",
            status=status,
            domain=domain,
        )

    def _score(val):
        return DimensionScore(value=val, confidence=0.7, reasoning="test")

    def _evaluation(unit_id: str, score: float, recommendation: str) -> UtilityEvaluation:
        return UtilityEvaluation(
            buildable_unit_id=unit_id,
            pain_severity=_score(8.0),
            addressable_scale=_score(7.0),
            build_effort=_score(6.0),
            composability=_score(7.0),
            competitive_density=_score(8.0),
            timing_fit=_score(7.0),
            compounding_value=_score(6.0),
            overall_score=score,
            recommendation=recommendation,
            weights_used={"pain_severity": 0.20},
        )

    seeds = [
        (_unit("bu-score-filter-1", "evaluated", "ai"), 84.0, "yes"),
        (_unit("bu-score-filter-2", "approved", "ai"), 88.0, "maybe"),
        (_unit("bu-score-filter-3", "evaluated", "devtools"), 86.0, "no"),
    ]
    for unit, score, recommendation in seeds:
        store.insert_buildable_unit(unit)
        store.insert_evaluation(_evaluation(unit.id, score, recommendation))
    store.insert_buildable_unit(_unit("bu-score-filter-unevaluated", "evaluated", "ai"))
    store.close()

    resp = client.get(
        "/api/v1/ideas/score-distribution?domain=ai&status=evaluated&bucket_size=10"
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["evaluated_count"] == 1
    assert data["unevaluated_count"] == 1
    assert data["buckets"] == [
        {
            "min_score": 80.0,
            "max_score": 90.0,
            "count": 1,
            "average_score": 84.0,
            "by_recommendation": {"yes": 1},
            "by_status": {"evaluated": 1},
        }
    ]


def test_get_evaluation_calibration(client, db_path):
    store = Store(db_path=db_path, wal_mode=True)

    def _unit(unit_id: str, domain: str) -> BuildableUnit:
        return BuildableUnit(
            id=unit_id,
            title=f"Idea {unit_id}",
            one_liner="A calibration API idea",
            category=BuildableCategory.CLI_TOOL,
            ideation_mode=IdeationMode.DIRECT,
            problem="Problem",
            solution="Solution",
            value_proposition="Value",
            domain=domain,
        )

    def _score(val):
        return DimensionScore(value=val, confidence=0.7, reasoning="test")

    def _evaluation(unit_id: str, score: float, recommendation: str) -> UtilityEvaluation:
        return UtilityEvaluation(
            buildable_unit_id=unit_id,
            pain_severity=_score(8.0),
            addressable_scale=_score(7.0),
            build_effort=_score(6.0),
            composability=_score(7.0),
            competitive_density=_score(8.0),
            timing_fit=_score(7.0),
            compounding_value=_score(6.0),
            overall_score=score,
            recommendation=recommendation,
            weights_used={"pain_severity": 0.20},
        )

    for unit_id, score, outcome in [
        ("bu-api-cal-1", 91.0, "approved"),
        ("bu-api-cal-2", 84.0, "rejected"),
        ("bu-api-cal-3", 44.0, "approved"),
    ]:
        store.insert_buildable_unit(_unit(unit_id, "devtools"))
        store.insert_evaluation(_evaluation(unit_id, score, "yes"))
        store.insert_feedback(unit_id, outcome)
    store.close()

    resp = client.get("/api/v1/evaluation/calibration?domain=devtools")

    assert resp.status_code == 200
    data = resp.json()
    assert data["domain"] == "devtools"
    assert data["total_groups"] == 1
    group = data["groups"][0]
    assert group["domain"] == "devtools"
    assert group["recommendation"] == "yes"
    assert group["sample_count"] == 3
    assert group["approval_rate"] == pytest.approx(0.6667)
    assert group["high_score_rejection_rate"] == pytest.approx(0.5)
    assert group["low_score_approval_rate"] == pytest.approx(1.0)


def test_get_roi_forecast(seeded_client):
    resp = seeded_client.get("/api/v1/roi-forecast?domain=testing")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_units"] == 1
    assert data["evaluated_units"] == 1
    assert data["results"][0]["idea_id"] == "bu-api001"
    assert data["results"][0]["roi_score"] > 0
    assert data["results"][0]["evidence_count"] == 2


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


def test_get_idea_evaluation_explanation(seeded_client):
    resp = seeded_client.get("/api/v1/ideas/bu-api001/evaluation-explanation")
    assert resp.status_code == 200
    data = resp.json()
    assert data["idea_id"] == "bu-api001"
    assert data["overall_score"] == 78.0
    assert data["recommendation"] == "yes"
    assert data["top_positive_drivers"]
    assert data["top_negative_drivers"]
    assert len(data["dimension_notes"]) == 7
    assert data["evidence_diversity"]["signal_count"] == 1
    assert data["recommended_next_evidence"]


def test_get_idea_evaluation_explanation_not_found(client):
    resp = client.get("/api/v1/ideas/nonexistent/evaluation-explanation")
    assert resp.status_code == 404


def test_get_idea_prior_art(seeded_client):
    resp = seeded_client.get("/api/v1/ideas/bu-api001/prior-art")
    assert resp.status_code == 200
    data = resp.json()
    assert data["idea_id"] == "bu-api001"
    assert data["prior_art_status"] == "weak_match"
    assert data["matches"][0]["source"] == "github"
    assert data["matches"][0]["relevance_score"] == 0.88
    assert data["matches"][0]["match_signals"] == {"stars": 42}


def test_get_idea_prior_art_not_found(client):
    resp = client.get("/api/v1/ideas/nonexistent/prior-art")
    assert resp.status_code == 404


def test_get_idea_publications(seeded_client, seeded_db):
    store = Store(db_path=seeded_db, wal_mode=True)
    first = store.insert_publication_attempt(
        idea_id="bu-api001",
        target_type="webhook",
        target_url="https://example.com/hook",
        status="failure",
        error="timeout",
    )
    second = store.insert_publication_attempt(
        idea_id="bu-api001",
        target_type="webhook",
        target_url="https://example.com/hook",
        status="success",
        response_status=202,
    )
    store.conn.execute(
        "UPDATE publication_history SET created_at = ? WHERE id = ?",
        ("2026-01-01T00:00:00+00:00", first["id"]),
    )
    store.conn.execute(
        "UPDATE publication_history SET created_at = ? WHERE id = ?",
        ("2026-01-02T00:00:00+00:00", second["id"]),
    )
    store.conn.commit()
    store.close()

    resp = seeded_client.get("/api/v1/ideas/bu-api001/publications")

    assert resp.status_code == 200
    data = resp.json()
    assert [attempt["id"] for attempt in data] == [second["id"], first["id"]]
    assert data[0]["response_status"] == 202
    assert data[1]["error"] == "timeout"


def test_get_idea_publications_not_found(client):
    resp = client.get("/api/v1/ideas/nonexistent/publications")
    assert resp.status_code == 404


def test_check_idea_prior_art_runs_checker(client, db_path):
    store = Store(db_path=db_path, wal_mode=True)
    unit = BuildableUnit(
        id="bu-prior001",
        title="Prior Art API Idea",
        one_liner="Check one idea through REST",
        category=BuildableCategory.CLI_TOOL,
        ideation_mode=IdeationMode.DIRECT,
        problem="No prior art API",
        solution="Expose prior art through REST",
        value_proposition="API clients can inspect novelty",
    )
    store.insert_buildable_unit(unit)
    store.close()

    result = PriorArtResult(
        buildable_unit_id="bu-prior001",
        matches=[
            PriorArtMatch(
                source="github",
                title="prior-art-api",
                url="https://github.com/example/prior-art-api",
                description="Existing implementation.",
                relevance_score=0.91,
                match_signals={"stars": 100},
                search_query="prior art api",
            )
        ],
        status="strong_match",
    )

    with patch("max.analysis.prior_art.check_prior_art", return_value=[result]) as mock_check:
        resp = client.post("/api/v1/ideas/bu-prior001/prior-art/check")

    assert resp.status_code == 200
    data = resp.json()
    assert data["prior_art_status"] == "strong_match"
    assert data["matches"][0]["title"] == "prior-art-api"
    mock_check.assert_called_once()


def test_check_idea_prior_art_force_replaces_matches(seeded_client):
    result = PriorArtResult(
        buildable_unit_id="bu-api001",
        matches=[
            PriorArtMatch(
                source="npm",
                title="new-prior-art",
                url="https://npmjs.com/package/new-prior-art",
                description="Replacement match.",
                relevance_score=0.72,
                match_signals={"downloads": 5},
                search_query="new prior art",
            )
        ],
        status="weak_match",
    )

    with patch("max.analysis.prior_art.check_prior_art", return_value=[result]):
        resp = seeded_client.post(
            "/api/v1/ideas/bu-api001/prior-art/check",
            json={"force": True},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert [match["title"] for match in data["matches"]] == ["new-prior-art"]
    assert data["matches"][0]["source"] == "npm"


def test_get_idea_spec_preview(seeded_client):
    resp = seeded_client.get("/api/v1/ideas/bu-api001/spec-preview")
    assert resp.status_code == 200
    data = resp.json()
    assert data["schema_version"] == "tact-spec-preview/v1"
    assert data["kind"] == "tact.project_spec"
    assert data["source"]["idea_id"] == "bu-api001"
    assert data["project"]["title"] == "Test Idea"
    assert data["problem"]["statement"] == "No test ideas"
    assert data["solution"]["approach"] == "Create a test idea"
    assert data["evidence"]["insight_ids"] == ["ins-api001"]
    assert data["evaluation"]["overall_score"] == 78.0
    assert data["evaluation"]["recommendation"] == "yes"


def test_get_idea_spec_preview_not_found(client):
    resp = client.get("/api/v1/ideas/nonexistent/spec-preview")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Idea not found: nonexistent"


def test_get_idea_spec_readiness_reports_incomplete_seeded_idea(seeded_client):
    resp = seeded_client.get("/api/v1/ideas/bu-api001/spec-readiness")
    assert resp.status_code == 200
    data = resp.json()
    assert data["idea_id"] == "bu-api001"
    assert data["status"] == "fail"
    assert data["passed"] is False
    assert "target_user" in data["failed_check_ids"]
    assert "validation_plan" in data["failed_check_ids"]
    assert "Name a specific user persona" in data["remediation"]


def test_get_idea_spec_readiness_not_found(client):
    resp = client.get("/api/v1/ideas/nonexistent/spec-readiness")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Idea not found: nonexistent"


def test_get_idea_implementation_plan(seeded_client):
    resp = seeded_client.get("/api/v1/ideas/bu-api001/implementation-plan")
    assert resp.status_code == 200
    data = resp.json()
    assert data["schema_version"] == "max-implementation-plan/v1"
    assert data["kind"] == "max.implementation_plan"
    assert data["idea_id"] == "bu-api001"
    assert data["source"]["spec_preview_schema_version"] == "tact-spec-preview/v1"
    assert data["summary"]["title"] == "Test Idea"
    assert data["summary"]["recommendation"] == "yes"
    assert [milestone["id"] for milestone in data["milestones"]] == ["M1", "M2", "M3", "M4"]
    assert any(task["id"] == "T3" for task in data["task_breakdown"])
    assert data["validation_steps"]
    assert data["expected_files_modules"]


def test_get_idea_implementation_plan_not_found(client):
    resp = client.get("/api/v1/ideas/nonexistent/implementation-plan")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Idea not found: nonexistent"


def test_get_idea_launch_checklist(seeded_client):
    resp = seeded_client.get("/api/v1/ideas/bu-api001/launch-checklist")
    assert resp.status_code == 200
    data = resp.json()
    assert data["schema_version"] == "max-launch-checklist/v1"
    assert data["kind"] == "max.launch_checklist"
    assert data["idea_id"] == "bu-api001"
    assert data["source"]["tact_spec_schema_version"] == "tact-spec-preview/v1"
    assert data["summary"]["title"] == "Test Idea"
    assert data["summary"]["recommendation"] == "yes"
    assert [section["id"] for section in data["sections"]] == [
        "repository_setup",
        "mvp_validation",
        "release_readiness",
        "telemetry",
        "risk_review",
        "feedback_capture",
    ]
    assert any(item["id"] == "LC1" for item in data["checklist_items"])
    assert data["risks"]


def test_get_idea_launch_checklist_not_found(client):
    resp = client.get("/api/v1/ideas/nonexistent/launch-checklist")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Idea not found: nonexistent"


def test_get_idea_experiment_card(seeded_client):
    resp = seeded_client.get("/api/v1/ideas/bu-api001/experiment-card")
    assert resp.status_code == 200
    data = resp.json()
    assert data["schema_version"] == "max-experiment-card/v1"
    assert data["kind"] == "max.experiment_card"
    assert data["idea_id"] == "bu-api001"
    assert data["source"]["evaluation_available"] is True
    assert data["source"]["recommendation"] == "yes"
    assert data["idea_summary"]["title"] == "Test Idea"
    assert data["primary_hypothesis"]
    assert data["target_participant"]["sample_size"] == 5
    assert data["minimum_viable_test"]["duration_days"] == 7
    assert data["success_metrics"]
    assert data["failure_signals"]
    assert len(data["seven_day_execution_plan"]) == 7
    assert set(data["decision_rules"]) == {"proceed", "iterate", "stop"}


def test_get_idea_experiment_card_not_found(client):
    resp = client.get("/api/v1/ideas/nonexistent/experiment-card")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Idea not found: nonexistent"


def test_get_idea_risk_register(seeded_client):
    resp = seeded_client.get("/api/v1/ideas/bu-api001/risk-register")
    assert resp.status_code == 200
    data = resp.json()
    assert data["schema_version"] == "max-risk-register/v1"
    assert data["kind"] == "max.risk_register"
    assert data["idea_id"] == "bu-api001"
    assert data["source"]["evidence_density_available"] is True
    assert data["source"]["contradictions_available"] is True
    assert data["risks"]
    assert any(risk["id"] == "missing_specific_user" for risk in data["risks"])


def test_get_idea_risk_register_not_found(client):
    resp = client.get("/api/v1/ideas/nonexistent/risk-register")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Idea not found: nonexistent"


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


def test_get_idea_evidence_density(seeded_client):
    resp = seeded_client.get("/api/v1/ideas/bu-api001/evidence-density")
    assert resp.status_code == 200
    data = resp.json()
    assert data["idea_id"] == "bu-api001"
    assert data["signal_count"] == 1
    assert data["insight_count"] == 1
    assert data["counts_by_source_adapter"] == {"test": 1}
    assert data["counts_by_source_type"] == {"forum": 1}
    assert data["average_credibility"] == 0.7
    assert data["density_score"] > 0
    assert data["missing_evidence_warnings"] == []


def test_get_idea_contradictions(client, db_path):
    store = Store(db_path=db_path, wal_mode=True)
    try:
        for signal_id, adapter, sentiment in [
            ("sig-conflict-positive", "forum-a", "positive"),
            ("sig-conflict-negative", "forum-b", "negative"),
        ]:
            store.insert_signal(
                Signal(
                    id=signal_id,
                    source_type=SignalSourceType.FORUM,
                    source_adapter=adapter,
                    title="Audit logs are required",
                    content="Evidence about audit logs",
                    url=f"https://example.com/{signal_id}",
                    credibility=0.8,
                    metadata={
                        "normalized_claim": "Audit logs are required",
                        "sentiment": sentiment,
                        "signal_role": "problem",
                    },
                )
            )
        store.insert_insight(
            Insight(
                id="ins-conflict-api",
                category=InsightCategory.GAP,
                title="Audit conflict",
                summary="Signals disagree",
                evidence=["sig-conflict-positive", "sig-conflict-negative"],
            )
        )
        store.insert_buildable_unit(
            BuildableUnit(
                id="bu-conflict-api",
                title="Conflict Idea",
                one_liner="Conflicting evidence",
                category=BuildableCategory.APPLICATION,
                problem="Conflicting evidence",
                solution="Review it",
                value_proposition="Better confidence",
                inspiring_insights=["ins-conflict-api"],
                evidence_signals=["sig-conflict-positive", "sig-conflict-negative"],
            )
        )
    finally:
        store.close()

    resp = client.get("/api/v1/ideas/bu-conflict-api/contradictions")
    assert resp.status_code == 200
    data = resp.json()
    assert data["entity_type"] == "idea"
    assert data["contradiction_count"] == 1
    assert data["contradictions"][0]["severity"] == "medium"
    assert set(data["contradictions"][0]["involved_signal_ids"]) == {
        "sig-conflict-positive",
        "sig-conflict-negative",
    }


def test_get_insight_contradictions_not_found(client):
    resp = client.get("/api/v1/insights/nonexistent/contradictions")
    assert resp.status_code == 404


def test_get_idea_evidence_density_not_found(client):
    resp = client.get("/api/v1/ideas/nonexistent/evidence-density")
    assert resp.status_code == 404


def test_get_idea_evidence_chain_not_found(client):
    resp = client.get("/api/v1/ideas/nonexistent/evidence-chain")
    assert resp.status_code == 404


def test_get_idea_lineage_graph(seeded_client):
    resp = seeded_client.get("/api/v1/ideas/bu-api001/lineage")
    assert resp.status_code == 200
    data = resp.json()
    nodes = {node["id"]: node for node in data["nodes"]}
    assert data["idea_id"] == "bu-api001"
    assert nodes["idea:bu-api001"]["label"] == "Test Idea"
    assert nodes["idea:bu-api001"]["type"] == "idea"
    assert nodes["buildable_unit:bu-api001"]["type"] == "buildable_unit"
    assert nodes["insight:ins-api001"]["label"] == "Test Insight"
    assert nodes["signal:sig-api001"]["evidence_links"] == ["https://example.com/test"]
    assert {
        (edge["source"], edge["target"], edge["type"])
        for edge in data["edges"]
    } == {
        ("idea:bu-api001", "buildable_unit:bu-api001", "materialized_as"),
        ("buildable_unit:bu-api001", "insight:ins-api001", "inspired_by"),
        ("insight:ins-api001", "signal:sig-api001", "supported_by"),
        ("buildable_unit:bu-api001", "signal:sig-api001", "direct_evidence"),
    }


def test_get_idea_lineage_graph_not_found(client):
    resp = client.get("/api/v1/ideas/nonexistent/lineage")
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


def test_get_idea_memory(seeded_client):
    resp = seeded_client.get("/api/v1/idea-memory?domain=testing&outcome=approved")
    assert resp.status_code == 200
    data = resp.json()
    assert data[0]["buildable_unit_id"] == "bu-api001"
    assert data[0]["domain"] == "testing"
    assert data[0]["outcome"] == "approved"
    assert data[0]["rejection_tags"] == []


def test_get_idea_memory_limit_clamped(client, db_path):
    store = Store(db_path=db_path, wal_mode=True)
    for i in range(101):
        store.insert_idea_memory(
            outcome="approved",
            pattern=f"Memory {i}",
            domain="testing",
        )
    store.close()

    resp = client.get("/api/v1/idea-memory?limit=150")
    assert resp.status_code == 200
    assert len(resp.json()) == 100


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


def test_evaluate_ideas_batch_evaluates_each_existing_idea_in_order(client, db_path):
    store = Store(db_path=db_path, wal_mode=True)
    for unit_id, title in [("bu-batch-1", "Batch Alpha"), ("bu-batch-2", "Batch Beta")]:
        store.insert_buildable_unit(
            BuildableUnit(
                id=unit_id,
                title=title,
                one_liner=f"{title} one liner",
                category=BuildableCategory.APPLICATION,
                problem="Problem",
                solution="Solution",
                value_proposition="Value",
            )
        )
    store.close()

    with patch("max.evaluation.engine.structured_call", return_value=_mock_evaluation_output()) as mock_call:
        resp = client.post(
            "/api/v1/ideas/evaluate-batch",
            json={"idea_ids": ["bu-batch-1", "bu-missing", "bu-batch-2"]},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert [item["idea_id"] for item in data["results"]] == [
        "bu-batch-1",
        "bu-missing",
        "bu-batch-2",
    ]
    assert [item["status"] for item in data["results"]] == ["evaluated", "error", "evaluated"]
    assert data["results"][0]["evaluation"]["recommendation"] == "yes"
    assert "Idea not found" in data["results"][1]["error"]
    assert mock_call.call_count == 2
    prompts = [call.kwargs["prompt"] for call in mock_call.call_args_list]
    assert "Batch Alpha" in prompts[0]
    assert "Batch Beta" in prompts[1]

    store = Store(db_path=db_path, wal_mode=True)
    try:
        assert store.get_buildable_unit("bu-batch-1").status == "evaluated"
        assert store.get_buildable_unit("bu-batch-2").status == "evaluated"
        assert store.get_evaluation("bu-batch-1") is not None
        assert store.get_evaluation("bu-batch-2") is not None
    finally:
        store.close()


def test_evaluate_ideas_batch_skip_existing(client, db_path):
    def _score(val):
        return DimensionScore(value=val, confidence=0.7, reasoning="existing")

    store = Store(db_path=db_path, wal_mode=True)
    for unit_id in ["bu-existing-eval", "bu-needs-eval"]:
        store.insert_buildable_unit(
            BuildableUnit(
                id=unit_id,
                title=unit_id,
                one_liner="one liner",
                category=BuildableCategory.APPLICATION,
                problem="Problem",
                solution="Solution",
                value_proposition="Value",
            )
        )
    store.insert_evaluation(
        UtilityEvaluation(
            buildable_unit_id="bu-existing-eval",
            pain_severity=_score(7.0),
            addressable_scale=_score(7.0),
            build_effort=_score(7.0),
            composability=_score(7.0),
            competitive_density=_score(7.0),
            timing_fit=_score(7.0),
            compounding_value=_score(7.0),
            overall_score=70.0,
            recommendation="maybe",
        )
    )
    store.close()

    with patch("max.evaluation.engine.structured_call", return_value=_mock_evaluation_output()) as mock_call:
        resp = client.post(
            "/api/v1/ideas/evaluate-batch",
            json={"idea_ids": ["bu-existing-eval", "bu-needs-eval"], "skip_existing": True},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert [item["status"] for item in data["results"]] == ["skipped", "evaluated"]
    assert data["results"][0]["evaluation"]["overall_score"] == 70.0
    assert mock_call.call_count == 1


def test_evaluate_ideas_batch_rejects_oversized_batch(client):
    resp = client.post(
        "/api/v1/ideas/evaluate-batch",
        json={"idea_ids": [f"bu-{i}" for i in range(26)]},
    )
    assert resp.status_code == 422


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


def test_feedback_rejects_invalid_status_transition(client, db_path):
    store = Store(db_path=db_path, wal_mode=True)
    try:
        store.insert_buildable_unit(
            BuildableUnit(
                id="bu-published",
                title="Published Idea",
                one_liner="Already shipped",
                category=BuildableCategory.APPLICATION,
                problem="Problem",
                solution="Solution",
                value_proposition="Value",
                status="published",
            )
        )
    finally:
        store.close()

    resp = client.post(
        "/api/v1/ideas/bu-published/feedback",
        json={"outcome": "rejected", "reason": "changed mind"},
    )

    assert resp.status_code == 409
    assert "published -> rejected" in resp.json()["detail"]

    store = Store(db_path=db_path, wal_mode=True)
    try:
        unit = store.get_buildable_unit("bu-published")
        assert unit is not None
        assert unit.status == "published"
        assert store.has_feedback("bu-published") is False
    finally:
        store.close()


def test_feedback_batch_mixed_success_failure_updates_statuses(client, db_path):
    store = Store(db_path=db_path, wal_mode=True)
    try:
        for unit_id, status in [
            ("bu-batch-approve", "evaluated"),
            ("bu-batch-reject", "evaluated"),
            ("bu-batch-published", "published"),
        ]:
            store.insert_buildable_unit(
                BuildableUnit(
                    id=unit_id,
                    title=f"Idea {unit_id}",
                    one_liner="Batch feedback idea",
                    category=BuildableCategory.APPLICATION,
                    problem="Problem",
                    solution="Solution",
                    value_proposition="Value",
                    status=status,
                )
            )
    finally:
        store.close()

    resp = client.post(
        "/api/v1/ideas/feedback-batch",
        json={
            "items": [
                {
                    "idea_id": "bu-batch-approve",
                    "outcome": "approved",
                    "reason": "strong",
                    "approval_score": 9,
                },
                {
                    "idea_id": "bu-batch-reject",
                    "outcome": "rejected",
                    "reason": "weak buyer",
                },
                {
                    "idea_id": "missing-batch-idea",
                    "outcome": "approved",
                },
                {
                    "idea_id": "bu-batch-published",
                    "outcome": "rejected",
                    "reason": "changed mind",
                },
            ]
        },
    )

    assert resp.status_code == 200
    results = {item["idea_id"]: item for item in resp.json()["results"]}
    assert results["bu-batch-approve"] == {
        "idea_id": "bu-batch-approve",
        "outcome": "approved",
        "status": "updated",
        "success": True,
        "error": None,
    }
    assert results["bu-batch-reject"]["status"] == "updated"
    assert results["bu-batch-reject"]["success"] is True
    assert results["missing-batch-idea"]["status"] == "not_found"
    assert results["missing-batch-idea"]["success"] is False
    assert "Idea not found" in results["missing-batch-idea"]["error"]
    assert results["bu-batch-published"]["status"] == "invalid_transition"
    assert results["bu-batch-published"]["success"] is False
    assert "published -> rejected" in results["bu-batch-published"]["error"]

    store = Store(db_path=db_path, wal_mode=True)
    try:
        approved = store.get_buildable_unit("bu-batch-approve")
        rejected = store.get_buildable_unit("bu-batch-reject")
        published = store.get_buildable_unit("bu-batch-published")
        assert approved is not None
        assert approved.status == "approved"
        assert rejected is not None
        assert rejected.status == "rejected"
        assert published is not None
        assert published.status == "published"

        feedback = store.get_latest_feedback("bu-batch-approve")
        assert feedback is not None
        assert feedback["outcome"] == "approved"
        assert feedback["reason"] == "strong"
        assert feedback["approval_score"] == 9
        assert store.has_feedback("bu-batch-published") is False
    finally:
        store.close()


def test_feedback_batch_requires_items(client):
    resp = client.post("/api/v1/ideas/feedback-batch", json={"items": []})
    assert resp.status_code == 422


def test_feedback_trends_endpoint(seeded_client):
    feedback_resp = seeded_client.post(
        "/api/v1/ideas/bu-api001/feedback",
        json={"outcome": "approved", "reason": "Great idea"},
    )
    assert feedback_resp.status_code == 201

    resp = seeded_client.get("/api/v1/trends/feedback?days=1&bucket=day")
    assert resp.status_code == 200
    data = resp.json()
    assert data["days"] == 1
    assert data["bucket"] == "day"
    assert data["total_count"] == 1
    assert data["approved_count"] == 1
    assert data["rejected_count"] == 0
    assert data["approval_rate"] == 1.0
    assert data["avg_score"] == 78.0

    active_windows = [window for window in data["windows"] if window["total_count"]]
    assert len(active_windows) == 1
    assert active_windows[0]["domains"] == [
        {
            "domain": "testing",
            "total_count": 1,
            "approved_count": 1,
            "rejected_count": 0,
            "approval_rate": 1.0,
            "avg_score": 78.0,
        }
    ]


def test_feedback_trends_endpoint_validates_query(client):
    assert client.get("/api/v1/trends/feedback?days=0").status_code == 422
    assert client.get("/api/v1/trends/feedback?bucket=hour").status_code == 422


def test_pipeline_trends_endpoint(pipeline_runs_client):
    resp = pipeline_runs_client.get("/api/v1/trends/pipeline?days=1&bucket=day")
    assert resp.status_code == 200
    data = resp.json()

    assert data["days"] == 1
    assert data["bucket"] == "day"
    assert data["window_count"] == 1
    assert data["run_count"] == 7
    assert data["completed_count"] == 5
    assert data["failed_count"] == 0
    assert data["signals_fetched"] == 150
    assert data["signals_new"] == 0
    assert data["insights_generated"] == 30
    assert data["ideas_generated"] == 15
    assert data["ideas_evaluated"] == 15
    assert data["estimated_cost_usd"] == pytest.approx(0.3375)
    assert data["avg_idea_score"] == 0.0

    assert len(data["windows"]) == 1
    assert data["windows"][0]["run_count"] == 7
    assert data["windows"][0]["completed_count"] == 5


def test_pipeline_trends_endpoint_validates_query(client):
    assert client.get("/api/v1/trends/pipeline?days=0").status_code == 422
    assert client.get("/api/v1/trends/pipeline?bucket=hour").status_code == 422


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


def test_update_design_brief_status(seeded_client):
    list_resp = seeded_client.get("/api/v1/design-briefs")
    brief = list_resp.json()[0]
    original_updated_at = datetime.fromisoformat(brief["updated_at"])

    resp = seeded_client.patch(
        f"/api/v1/design-briefs/{brief['id']}/status",
        json={"status": "approved"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == brief["id"]
    assert data["design_status"] == "approved"
    assert datetime.fromisoformat(data["updated_at"]) > original_updated_at


def test_update_design_brief_status_rejects_invalid_status(seeded_client):
    list_resp = seeded_client.get("/api/v1/design-briefs")
    brief_id = list_resp.json()[0]["id"]

    resp = seeded_client.patch(
        f"/api/v1/design-briefs/{brief_id}/status",
        json={"status": "designing"},
    )

    assert resp.status_code == 422


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


def test_get_design_brief_validation_plan(seeded_client):
    list_resp = seeded_client.get("/api/v1/design-briefs")
    brief_id = list_resp.json()[0]["id"]

    resp = seeded_client.get(f"/api/v1/design-briefs/{brief_id}/validation-plan")

    assert resp.status_code == 200
    data = resp.json()
    assert data["schema_version"] == "max.design_brief.validation_plan.v1"
    assert data["design_brief"]["id"] == brief_id
    assert data["target_user_hypotheses"]
    assert data["recruiting_criteria"]["screener_questions"]
    assert data["interview_script"]["problem_discovery_questions"]
    assert data["smoke_test_landing_page_copy"]["headline"] == "Test Design Brief"
    assert data["success_metrics"]
    assert data["failure_thresholds"]
    assert data["two_week_timeline"]


def test_synthesize_design_briefs_persists_approved_and_published(client, db_path):
    def _score(value: float) -> DimensionScore:
        return DimensionScore(value=value, confidence=0.8, reasoning="seeded")

    def _unit(unit_id: str, title: str, *, domain: str, status: str) -> BuildableUnit:
        return BuildableUnit(
            id=unit_id,
            title=title,
            one_liner="Adversarial API workflow benchmark for tool-using agents",
            category=BuildableCategory.APPLICATION,
            ideation_mode=IdeationMode.DIRECT,
            problem="Teams cannot validate agent workflow security before deployment.",
            solution="Run API workflow fixtures with embedded attack payloads.",
            value_proposition="Ship safer agents with repeatable release checks.",
            specific_user="platform engineer deploying AI agents",
            buyer="engineering manager",
            workflow_context="CI gate before agent production deployment",
            current_workaround="Manual prompt testing",
            why_now="MCP adoption makes agent tool security urgent.",
            validation_plan="Run against three agent frameworks and publish scorecards.",
            first_10_customers="Agent framework maintainers and platform teams",
            tech_approach="Python service with YAML fixtures and a REST API",
            domain=domain,
            status=status,
            quality_score=8.0,
            domain_risks=["Framework APIs may change quickly"],
        )

    def _evaluation(unit_id: str, score: float) -> UtilityEvaluation:
        return UtilityEvaluation(
            buildable_unit_id=unit_id,
            pain_severity=_score(8.0),
            addressable_scale=_score(7.0),
            build_effort=_score(8.0),
            composability=_score(7.5),
            competitive_density=_score(7.0),
            timing_fit=_score(8.0),
            compounding_value=_score(7.0),
            overall_score=score,
            strengths=["clear buyer"],
            weaknesses=[],
            recommendation="yes",
            weights_used={"pain_severity": 0.2},
        )

    store = Store(db_path=db_path, wal_mode=True)
    try:
        seeds = [
            (_unit("bu-synth-approved", "AgentAdversarialBench", domain="testing", status="approved"), 84, "approved", 9),
            (_unit("bu-synth-published", "AgentAPIProbe", domain="testing", status="published"), 78, "published", 8),
            (_unit("bu-synth-rejected", "Rejected Agent Probe", domain="testing", status="rejected"), 91, "rejected", None),
            (_unit("bu-synth-other", "Other Domain Agent Probe", domain="other", status="approved"), 88, "approved", 10),
        ]
        for unit, score, outcome, approval_score in seeds:
            store.insert_buildable_unit(unit)
            store.insert_evaluation(_evaluation(unit.id, score))
            store.insert_feedback(unit.id, outcome, "seeded review", approval_score=approval_score)
    finally:
        store.close()

    resp = client.post("/api/v1/design-briefs/synthesize?domain=testing&top=1")

    assert resp.status_code == 201
    data = resp.json()
    assert len(data) == 1
    brief = data[0]
    assert brief["domain"] == "testing"
    assert brief["lead_idea_id"] in {"bu-synth-approved", "bu-synth-published"}
    assert set(brief["source_idea_ids"]) == {"bu-synth-approved", "bu-synth-published"}
    assert {source["idea_id"] for source in brief["sources"]} == {
        "bu-synth-approved",
        "bu-synth-published",
    }

    list_resp = client.get("/api/v1/design-briefs?domain=testing")
    assert list_resp.status_code == 200
    persisted = list_resp.json()
    assert [item["id"] for item in persisted] == [brief["id"]]


def test_get_design_brief_markdown_not_found(client):
    resp = client.get("/api/v1/design-briefs/dbf-missing/markdown")
    assert resp.status_code == 404


def test_get_design_brief_validation_plan_not_found(client):
    resp = client.get("/api/v1/design-briefs/dbf-missing/validation-plan")
    assert resp.status_code == 404


def test_get_design_brief_not_found(client):
    resp = client.get("/api/v1/design-briefs/dbf-missing")
    assert resp.status_code == 404


def test_update_design_brief_status_not_found(client):
    resp = client.patch(
        "/api/v1/design-briefs/dbf-missing/status",
        json={"status": "approved"},
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


def test_opportunity_heatmap_endpoint(seeded_client):
    resp = seeded_client.get("/api/v1/opportunity-heatmap")
    assert resp.status_code == 200
    data = resp.json()
    assert data[0]["domain"] == "testing"
    assert data[0]["idea_category"] == "application"
    assert data[0]["signal_count"] == 1
    assert data[0]["insight_count"] == 1
    assert data[0]["idea_count"] == 1
    assert data[0]["evaluated_count"] == 1
    assert data[0]["average_score"] == 78.0
    assert data[0]["opportunity_score"] > 0


def test_ideas_opportunity_heatmap_alias(seeded_client):
    resp = seeded_client.get("/api/v1/ideas/opportunity-heatmap?domain=testing")
    assert resp.status_code == 200
    assert resp.json()[0]["domain"] == "testing"


# ── Adapter endpoints ───────────────────────────────────────────────


def test_adapters_endpoint_reports_config_metadata(client):
    from max.sources.registry import AdapterMetadata

    with patch(
        "max.server.api.list_adapter_metadata",
        return_value=[
            AdapterMetadata(
                name="rss_feed",
                config_keys=["feeds", "tags", "max_age_days"],
                required_keys=["feeds"],
                description="Fetches RSS or Atom entries.",
            )
        ],
    ):
        resp = client.get("/api/v1/adapters")

    assert resp.status_code == 200
    data = resp.json()
    assert data == [
        {
            "name": "rss_feed",
            "config_keys": ["feeds", "tags", "max_age_days"],
            "required_keys": ["feeds"],
            "description": "Fetches RSS or Atom entries.",
        }
    ]


def test_adapter_circuit_breakers_include_known_and_registry_adapters(client):
    from max.sources.base import get_circuit_breaker

    registry_only = "api_registry_only"
    cb = get_circuit_breaker(registry_only)
    cb.record_failure()

    with patch("max.server.api.list_adapters", return_value=["known_adapter"]):
        resp = client.get("/api/v1/adapters/circuit-breakers")

    assert resp.status_code == 200
    data = resp.json()
    by_name = {row["adapter_name"]: row for row in data}
    assert by_name["known_adapter"]["state"] == "closed"
    assert by_name["known_adapter"]["failure_count"] == 0
    assert by_name[registry_only]["state"] == "closed"
    assert by_name[registry_only]["failure_count"] == 1
    assert by_name[registry_only]["last_failure_at"] is not None
    assert by_name[registry_only]["retry_after"] > 0


def test_adapter_health_reports_registry_stats_breakers_and_approval_rates(seeded_client):
    from max.sources.base import get_circuit_breaker

    cb = get_circuit_breaker("test")
    cb.record_failure()

    seeded_client.post(
        "/api/v1/ideas/bu-api001/feedback",
        json={"outcome": "approved", "reason": "useful"},
    )

    with patch("max.server.api.list_adapters", return_value=["test", "unused"]):
        resp = seeded_client.get("/api/v1/adapters/health")

    assert resp.status_code == 200
    data = resp.json()
    assert data["profile"] is None
    assert data["registered_adapters"] == ["test", "unused"]
    assert data["enabled_profile_sources"] == []

    by_name = {row["adapter_name"]: row for row in data["adapters"]}
    assert by_name["test"]["registered"] is True
    assert by_name["test"]["enabled_for_profile"] is None
    assert by_name["test"]["total_signals"] == 1
    assert by_name["test"]["insight_hit_rate"] == 1.0
    assert by_name["test"]["idea_hit_rate"] == 1.0
    assert by_name["test"]["total_feedbacked"] == 1
    assert by_name["test"]["approved"] == 1
    assert by_name["test"]["approval_rate"] == 1.0
    assert by_name["test"]["circuit_breaker"]["failure_count"] == 1
    assert by_name["unused"]["total_signals"] == 0


def test_adapter_health_resolves_enabled_profile_sources(client):
    profile = _profile_endpoint_fixture("devtools", "developer-tools")

    with (
        patch("max.server.api.list_adapters", return_value=["hackernews", "reddit"]),
        patch("max.profiles.loader.load_profile", return_value=profile),
    ):
        resp = client.get("/api/v1/adapters/health?profile=devtools")

    assert resp.status_code == 200
    data = resp.json()
    assert data["profile"] == "devtools"
    assert data["enabled_profile_sources"] == ["hackernews"]
    by_name = {row["adapter_name"]: row for row in data["adapters"]}
    assert by_name["hackernews"]["enabled_for_profile"] is True
    assert by_name["reddit"]["enabled_for_profile"] is False


def test_adapter_health_unknown_profile_returns_404(client):
    with patch("max.profiles.loader.load_profile", side_effect=FileNotFoundError("missing")):
        resp = client.get("/api/v1/adapters/health?profile=missing")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Profile not found: missing"


def test_fetch_allocation_explain_reports_profile_inputs_and_final_limits(seeded_client):
    from max.profiles.schema import DomainContext, PipelineProfile, SourceConfig

    profile = PipelineProfile(
        name="explain",
        domain=DomainContext(
            name="testing",
            description="testing domain",
            categories=["application"],
            target_user_types=["developers"],
        ),
        sources=[
            SourceConfig(adapter="test", weight=2.5),
            SourceConfig(adapter="unused", enabled=False, weight=0.25),
        ],
    )

    seeded_client.post(
        "/api/v1/ideas/bu-api001/feedback",
        json={"outcome": "approved", "reason": "useful"},
    )

    with (
        patch("max.profiles.loader.load_profile", return_value=profile),
        patch(
            "max.pipeline.fetch_strategy.compute_fetch_allocation",
            return_value={"test": 17},
        ) as mock_allocation,
    ):
        resp = seeded_client.get(
            "/api/v1/fetch/allocation-explain?profile=explain&total_budget=17"
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["profile"] == "explain"
    assert data["total_budget"] == 17
    assert data["allocation"] == {"test": 17}
    mock_allocation.assert_called_once()
    assert mock_allocation.call_args.args[0] == 17
    assert mock_allocation.call_args.args[1] == ["test"]

    by_name = {row["adapter_name"]: row for row in data["adapters"]}
    assert by_name["test"]["enabled"] is True
    assert by_name["test"]["configured_weight"] == 2.5
    assert by_name["test"]["total_signals"] == 1
    assert by_name["test"]["insight_hit_rate"] == 1.0
    assert by_name["test"]["idea_hit_rate"] == 1.0
    assert by_name["test"]["approval_rate"] == 1.0
    assert by_name["test"]["allocated_limit"] == 17
    assert by_name["unused"]["enabled"] is False
    assert by_name["unused"]["configured_weight"] == 0.25
    assert by_name["unused"]["approval_rate"] is None
    assert by_name["unused"]["allocated_limit"] == 0


def test_fetch_allocation_explain_unknown_profile_returns_404(client):
    with patch("max.profiles.loader.load_profile", side_effect=FileNotFoundError("missing")):
        resp = client.get("/api/v1/fetch/allocation-explain?profile=missing&total_budget=10")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Profile not found: missing"


# ── Similarity endpoint ────────────────────────────────────────────


def test_get_similar_ideas_by_query(client, db_path):
    store = Store(db_path=db_path, wal_mode=True)
    try:
        store.insert_buildable_unit(
            BuildableUnit(
                id="bu-similar-api",
                title="MCP Test Runner",
                one_liner="MCP server testing for CI",
                category=BuildableCategory.APPLICATION,
                problem="MCP servers need repeatable CI testing",
                solution="Create a protocol test runner",
                value_proposition="Find MCP server regressions earlier",
            )
        )
        store.insert_buildable_unit(
            BuildableUnit(
                id="bu-different-api",
                title="Payroll Exporter",
                one_liner="Payroll CSV cleanup",
                category=BuildableCategory.APPLICATION,
                problem="Payroll teams need cleaner exports",
                solution="Normalize payroll CSV files",
                value_proposition="Reduce payroll corrections",
            )
        )
    finally:
        store.close()

    resp = client.get("/api/v1/ideas/similar?query=MCP%20server%20testing&threshold=0.2")

    assert resp.status_code == 200
    data = resp.json()
    assert [item["idea_id"] for item in data] == ["bu-similar-api"]
    assert data[0]["title"] == "MCP Test Runner"
    assert data[0]["problem_summary"] == "MCP servers need repeatable CI testing"
    assert data[0]["similarity_score"] > 0.2
    assert data[0]["overlapping_evidence_ids"] == []
    assert data[0]["overlapping_insight_ids"] == []


def test_post_similar_ideas_by_idea_id_reports_overlap(client, db_path):
    store = Store(db_path=db_path, wal_mode=True)
    try:
        store.insert_buildable_unit(
            BuildableUnit(
                id="bu-similar-query",
                title="MCP Test Runner",
                one_liner="MCP server testing",
                category=BuildableCategory.APPLICATION,
                problem="MCP servers need repeatable testing",
                solution="Create a test runner",
                value_proposition="Find regressions earlier",
                inspiring_insights=["ins-shared", "ins-query"],
                evidence_signals=["sig-shared", "sig-query"],
            )
        )
        store.insert_buildable_unit(
            BuildableUnit(
                id="bu-similar-match",
                title="MCP Validator",
                one_liner="MCP server validation",
                category=BuildableCategory.APPLICATION,
                problem="MCP servers need protocol validation testing",
                solution="Create a validator",
                value_proposition="Reduce protocol bugs",
                inspiring_insights=["ins-shared"],
                evidence_signals=["sig-shared"],
            )
        )
    finally:
        store.close()

    resp = client.post(
        "/api/v1/ideas/similar",
        json={"idea_id": "bu-similar-query", "threshold": 0.1, "limit": 5},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data[0]["idea_id"] == "bu-similar-match"
    assert data[0]["overlapping_evidence_ids"] == ["sig-shared"]
    assert data[0]["overlapping_insight_ids"] == ["ins-shared"]


def test_similar_ideas_requires_one_query(client):
    resp = client.get("/api/v1/ideas/similar")
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Provide exactly one of idea_id or query"


def test_get_portfolio_overlap_returns_clusters(client, db_path):
    store = Store(db_path=db_path, wal_mode=True)
    try:
        store.insert_buildable_unit(
            BuildableUnit(
                id="bu-overlap-a",
                title="MCP Test Runner",
                one_liner="MCP maintainers need protocol testing",
                category=BuildableCategory.APPLICATION,
                problem="MCP maintainers need repeatable protocol testing",
                solution="Create a test runner",
                target_users="devtools teams",
                specific_user="platform engineer",
                value_proposition="Find regressions earlier",
                evidence_signals=["sig-shared", "sig-a"],
                tech_approach="TypeScript CLI",
                suggested_stack={"language": "typescript", "runtime": "node"},
                status="evaluated",
            )
        )
        store.insert_buildable_unit(
            BuildableUnit(
                id="bu-overlap-b",
                title="MCP Validator",
                one_liner="MCP maintainers need validation testing",
                category=BuildableCategory.APPLICATION,
                problem="MCP maintainers need protocol validation testing",
                solution="Create a validator",
                target_users="devtools teams",
                specific_user="platform engineer",
                value_proposition="Reduce protocol bugs",
                evidence_signals=["sig-shared", "sig-b"],
                tech_approach="TypeScript service",
                suggested_stack={"language": "typescript", "runtime": "node"},
                status="evaluated",
            )
        )
    finally:
        store.close()

    resp = client.get("/api/v1/ideas/portfolio-overlap?min_overlap_score=0.25")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["idea_ids"] == ["bu-overlap-a", "bu-overlap-b"]
    assert data[0]["representative_idea_ids"] == ["bu-overlap-a", "bu-overlap-b"]
    assert data[0]["suggested_action"] in {"merge", "differentiate"}
    assert "evidence_signal_ids" in {reason["type"] for reason in data[0]["overlap_reasons"]}


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


def test_update_schedule_pipeline_config(schedule_client):
    resp = schedule_client.post(
        "/api/v1/schedule",
        json={
            "profile": "devtools",
            "include_all": True,
            "signal_limit": 45,
            "min_score": 62.5,
            "weight_profile": "quick_wins",
            "ideation_mode": "refinement",
            "quality_loop_enabled": True,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["profile"] == "devtools"
    assert data["include_all"] is True
    assert data["pipeline_config"]["signal_limit"] == 45
    assert data["pipeline_config"]["min_score"] == 62.5
    assert data["pipeline_config"]["weight_profile"] == "quick_wins"
    assert data["pipeline_config"]["ideation_mode"] == "refinement"
    assert data["pipeline_config"]["quality_loop_enabled"] is True


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
                token_usage=(
                    {"total_input": i * 1000, "total_output": i * 100}
                    if i == 1
                    else {"input": i * 1000, "output": i * 100}
                ),
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


def test_compare_pipeline_runs_endpoint(client, db_path):
    _seed_api_pipeline_run(
        db_path,
        "run-compare-base",
        signals_fetched=4,
        ideas_generated=1,
        adapter_metrics={"github": {"status": "ok", "signal_count": 4, "duration_ms": 50}},
    )
    _seed_api_pipeline_run(
        db_path,
        "run-compare-target",
        signals_fetched=9,
        ideas_generated=3,
        adapter_metrics={"github": {"status": "ok", "signal_count": 9, "duration_ms": 70}},
    )

    resp = client.get(
        "/api/v1/pipeline/runs/compare"
        "?base_run_id=run-compare-base&target_run_id=run-compare-target"
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["fetched_signals"]["signals_fetched"]["delta"] == 5
    assert data["generated_ideas"]["ideas_generated"]["delta"] == 2
    assert data["adapter_metrics"][0]["metrics"]["signal_count"]["delta"] == 5


def test_compare_pipeline_runs_endpoint_missing_run_returns_404(client, db_path):
    _seed_api_pipeline_run(
        db_path,
        "run-compare-base",
        signals_fetched=4,
        ideas_generated=1,
        adapter_metrics={},
    )

    resp = client.get(
        "/api/v1/pipeline/runs/compare"
        "?base_run_id=run-compare-base&target_run_id=run-not-found"
    )

    assert resp.status_code == 404
    assert resp.json()["detail"]["missing_run_ids"] == ["run-not-found"]


def test_llm_usage_aggregates_pipeline_runs(pipeline_runs_client):
    resp = pipeline_runs_client.get("/api/v1/usage/llm")
    assert resp.status_code == 200
    data = resp.json()

    assert data["limit"] == 20
    assert data["run_count"] == 7
    assert data["total_input"] == 15_000
    assert data["total_output"] == 1_500
    assert data["total_cost_usd"] == pytest.approx(0.3375)
    assert len(data["runs"]) == 7
    assert {run["id"] for run in data["runs"]} == {f"run-{i:03d}" for i in range(1, 8)}

    run_001 = next(run for run in data["runs"] if run["id"] == "run-001")
    assert run_001["total_input"] == 1000
    assert run_001["total_output"] == 100
    assert run_001["total_cost_usd"] == pytest.approx(0.0225)


def test_llm_usage_limit(pipeline_runs_client):
    resp = pipeline_runs_client.get("/api/v1/usage/llm?limit=3")
    assert resp.status_code == 200
    data = resp.json()
    assert data["limit"] == 3
    assert data["run_count"] == 3
    assert len(data["runs"]) == 3


def test_llm_usage_empty(client):
    resp = client.get("/api/v1/usage/llm")
    assert resp.status_code == 200
    assert resp.json() == {
        "limit": 20,
        "run_count": 0,
        "total_input": 0,
        "total_output": 0,
        "total_cost_usd": 0.0,
        "runs": [],
    }


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
                estimated_input_tokens=0,
                estimated_output_tokens=0,
                estimated_total_tokens=0,
                estimated_cost_usd=0.0,
            )
        ],
        estimated_total_llm_calls=0,
        estimated_token_budget=0,
        estimated_input_tokens=0,
        estimated_output_tokens=0,
        estimated_cost_usd=0.0,
        cost_by_stage={},
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
        "profile_name": "devtools",
        "domain": "developer-tools",
        "enabled_adapters": [],
        "fetch_allocation": {},
        "effective_config": {
            "signal_limit": 12,
            "min_score": 50.0,
            "weight_profile": "default",
            "ideation_mode": "direct",
            "quality_loop_enabled": False,
            "draft_count": 8,
        },
        "stages": [
            {
                "name": "fetch",
                "would_process": 12,
                "estimated_llm_calls": 0,
                "skipped": False,
                "reason": "",
                "estimated_input_tokens": 0,
                "estimated_output_tokens": 0,
                "estimated_total_tokens": 0,
                "estimated_cost_usd": 0.0,
            }
        ],
        "estimated_total_llm_calls": 0,
        "estimated_token_budget": 0,
        "estimated_input_tokens": 0,
        "estimated_output_tokens": 0,
        "estimated_cost_usd": 0.0,
        "cost_by_stage": {},
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
