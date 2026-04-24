"""API tests for idea product brief export."""

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
def product_brief_db(tmp_path) -> str:
    db_path = str(tmp_path / "product_brief_api.db")
    with Store(db_path=db_path, wal_mode=True) as store:
        store.insert_signal(
            Signal(
                id="sig-api-brief001",
                source_type=SignalSourceType.FORUM,
                source_adapter="test",
                title="API brief signal",
                content="API consumers need a markdown brief.",
                url="https://example.com/api-brief",
                credibility=0.8,
            )
        )
        store.insert_insight(
            Insight(
                id="ins-api-brief001",
                category=InsightCategory.GAP,
                title="API brief insight",
                summary="Product reviewers need markdown from one endpoint.",
                evidence=["sig-api-brief001"],
                confidence=0.8,
                domains=["testing"],
            )
        )
        store.insert_buildable_unit(_api_brief_unit())
        store.insert_evaluation(_api_brief_evaluation())
        store.create_validation_experiment(
            "bu-api-brief001",
            hypothesis="Markdown brief improves review flow",
            method="Reviewer walkthrough",
            success_metric="Reviewers make a decision from the brief",
            status="completed",
            completed_at="2026-04-25T00:00:00+00:00",
            result_summary="Reviewers approved the format",
            evidence_urls=["https://example.com/api-validation"],
            confidence_delta=0.2,
        )
    return db_path


@pytest.fixture
def product_brief_client(product_brief_db: str) -> TestClient:
    from max.server.dependencies import get_store

    app = create_app()

    def override_get_store():
        store = Store(db_path=product_brief_db, wal_mode=True)
        try:
            yield store
        finally:
            store.close()

    app.dependency_overrides[get_store] = override_get_store
    return TestClient(app)


def test_get_product_brief_json_returns_markdown_and_source_ids(
    product_brief_client: TestClient,
) -> None:
    response = product_brief_client.get("/api/v1/ideas/bu-api-brief001/product-brief")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == "max-product-brief/v1"
    assert payload["idea_id"] == "bu-api-brief001"
    assert "## Problem" in payload["markdown"]
    assert "## Evidence" in payload["markdown"]
    assert "## Validation Plan" in payload["markdown"]
    assert payload["source_ids"]["idea_ids"] == ["bu-api-brief001"]
    assert payload["source_ids"]["evaluation_ids"] == ["bu-api-brief001"]
    assert payload["source_ids"]["insight_ids"] == ["ins-api-brief001"]
    assert payload["source_ids"]["signal_ids"] == ["sig-api-brief001"]
    assert len(payload["source_ids"]["validation_experiment_ids"]) == 1


def test_get_product_brief_markdown_response(product_brief_client: TestClient) -> None:
    response = product_brief_client.get("/api/v1/ideas/bu-api-brief001/product-brief.md")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.text.startswith("# API Product Brief Product Brief")
    assert "## Evaluation" in response.text
    assert "Utility score: 81.0" in response.text


def test_get_product_brief_query_flags_omit_optional_sections(
    product_brief_client: TestClient,
) -> None:
    response = product_brief_client.get(
        "/api/v1/ideas/bu-api-brief001/product-brief?include_evidence=false&include_validation=false"
    )

    assert response.status_code == 200
    payload = response.json()
    assert "## Evidence" not in payload["markdown"]
    assert "## Validation Plan" not in payload["markdown"]
    assert payload["source_ids"]["signal_ids"] == []
    assert payload["source_ids"]["validation_experiment_ids"] == []


def test_get_product_brief_missing_idea_returns_404(
    product_brief_client: TestClient,
) -> None:
    response = product_brief_client.get("/api/v1/ideas/bu-missing/product-brief")

    assert response.status_code == 404
    assert response.json()["detail"] == "Idea not found: bu-missing"


def test_get_product_brief_markdown_missing_idea_returns_404(
    product_brief_client: TestClient,
) -> None:
    response = product_brief_client.get("/api/v1/ideas/bu-missing/product-brief.md")

    assert response.status_code == 404
    assert response.json()["detail"] == "Idea not found: bu-missing"


def _api_brief_unit() -> BuildableUnit:
    return BuildableUnit(
        id="bu-api-brief001",
        title="API Product Brief",
        one_liner="Export concise idea briefs through the API",
        category=BuildableCategory.APPLICATION,
        ideation_mode=IdeationMode.DIRECT,
        problem="Product reviewers lack a compact artifact before spec generation.",
        solution="Return Markdown and source IDs from a product brief endpoint.",
        target_users="humans",
        value_proposition="Human reviewers can approve or revise ideas faster.",
        specific_user="product reviewer",
        buyer="platform lead",
        workflow_context="pre-spec product review",
        current_workaround="Reading the idea detail response and spec bundle separately.",
        why_now="Idea volume has increased.",
        validation_plan="Compare review time with and without the brief.",
        first_10_customers="internal product reviewers",
        domain_risks=["Markdown may become too verbose."],
        evidence_rationale="Evidence supports a compact review artifact.",
        inspiring_insights=["ins-api-brief001"],
        evidence_signals=["sig-api-brief001"],
        prior_art_status="clear",
    )


def _api_brief_evaluation() -> UtilityEvaluation:
    score = DimensionScore(value=8.0, confidence=0.75, reasoning="seeded")
    return UtilityEvaluation(
        buildable_unit_id="bu-api-brief001",
        pain_severity=score,
        addressable_scale=score,
        build_effort=score,
        composability=score,
        competitive_density=score,
        timing_fit=score,
        compounding_value=score,
        overall_score=81.0,
        strengths=["Compact handoff"],
        weaknesses=["Needs format discipline"],
        recommendation="yes",
        weights_used={"pain_severity": 0.2},
    )
