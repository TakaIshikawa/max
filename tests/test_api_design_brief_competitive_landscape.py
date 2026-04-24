from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from max.analysis.design_brief_competitive_landscape import SCHEMA_VERSION
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.server.app import create_app
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit
from max.types.evaluation import DimensionScore, UtilityEvaluation


def _unit(unit_id: str) -> BuildableUnit:
    return BuildableUnit(
        id=unit_id,
        title="Competitive API Idea",
        one_liner="Competitive landscape API source idea",
        category="application",
        problem="Design brief consumers need competitor context before handoff.",
        solution="Return stored prior-art clusters and differentiation guidance.",
        value_proposition="Improve design handoff positioning.",
        specific_user="product engineer",
        buyer="product lead",
        workflow_context="design brief implementation planning",
        validation_plan="Review with product leads.",
        domain="developer-tools",
        status="approved",
    )


def _evaluation(unit_id: str) -> UtilityEvaluation:
    dim = DimensionScore(value=7.0, confidence=0.7, reasoning="seeded")
    return UtilityEvaluation(
        buildable_unit_id=unit_id,
        pain_severity=dim,
        addressable_scale=dim,
        build_effort=dim,
        composability=dim,
        competitive_density=DimensionScore(value=5.0, confidence=0.7, reasoning="stored prior art"),
        timing_fit=dim,
        compounding_value=dim,
        overall_score=76.0,
        strengths=["handoff-ready"],
        weaknesses=["competition exists"],
        recommendation="yes",
        weights_used={"competitive_density": 0.1},
    )


def _seed_brief(db_path: str, *, with_prior_art: bool = True) -> str:
    store = Store(db_path=db_path, wal_mode=True)
    try:
        unit = _unit("bu-api-competitive")
        store.insert_buildable_unit(unit)
        store.insert_evaluation(_evaluation(unit.id))
        if with_prior_art:
            store.insert_prior_art_match(
                unit.id,
                {
                    "source": "github",
                    "title": "existing-brief-landscape",
                    "url": "https://github.com/example/existing-brief-landscape",
                    "description": "Stored prior-art record for competitive landscape handoff.",
                    "relevance_score": 0.86,
                    "match_signals": {"stars": 54},
                    "search_query": "design brief competitive landscape",
                },
            )
            store.update_prior_art_status(unit.id, "weak_match")
        return store.insert_design_brief(
            ProjectBrief(
                title="Competitive Landscape API Brief",
                domain="developer-tools",
                theme="competitive-handoff",
                lead=Candidate(unit=unit),
                readiness_score=80.0,
                why_this_now="Design briefs need positioning before implementation.",
                merged_product_concept="A deterministic competitive landscape API.",
                synthesis_rationale="Single source idea for API handoff.",
                mvp_scope=["Competitive landscape endpoint"],
                first_milestones=["Return stored prior-art clusters"],
                validation_plan="Call the API in implementation planning.",
                risks=["Competitor data may be sparse."],
                source_idea_ids=[unit.id],
            )
        )
    finally:
        store.close()


@pytest.fixture
def competitive_client(tmp_path):
    db_path = str(tmp_path / "api.db")
    brief_id = _seed_brief(db_path)

    from max.server.dependencies import get_store

    app = create_app()

    def override_get_store():
        store = Store(db_path=db_path, wal_mode=True)
        try:
            yield store
        finally:
            store.close()

    app.dependency_overrides[get_store] = override_get_store
    return TestClient(app), brief_id


def test_get_design_brief_competitive_landscape_rest_response(competitive_client) -> None:
    client, brief_id = competitive_client
    response = client.get(f"/api/v1/design-briefs/{brief_id}/competitive-landscape")

    assert response.status_code == 200
    data = response.json()
    assert data["schema_version"] == SCHEMA_VERSION
    assert data["design_brief"]["id"] == brief_id
    assert data["status"] == "ready"
    assert data["summary"]["prior_art_record_count"] == 1
    assert data["competitor_clusters"][0]["top_competitors"][0]["title"] == "existing-brief-landscape"
    assert data["differentiation_angles"]
    assert data["recommended_positioning"]


def test_get_design_brief_competitive_landscape_empty_prior_art(tmp_path) -> None:
    db_path = str(tmp_path / "api.db")
    brief_id = _seed_brief(db_path, with_prior_art=False)

    from max.server.dependencies import get_store

    app = create_app()

    def override_get_store():
        store = Store(db_path=db_path, wal_mode=True)
        try:
            yield store
        finally:
            store.close()

    app.dependency_overrides[get_store] = override_get_store
    client = TestClient(app)

    response = client.get(f"/api/v1/design-briefs/{brief_id}/competitive-landscape")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "insufficient_data"
    assert data["summary"]["insufficient_data_reasons"]
    assert data["competitor_clusters"] == []


def test_get_design_brief_competitive_landscape_not_found(competitive_client) -> None:
    client, _brief_id = competitive_client
    response = client.get("/api/v1/design-briefs/dbf-missing/competitive-landscape")

    assert response.status_code == 404
    assert response.json()["detail"] == "Design brief not found: dbf-missing"
