"""API tests for design brief competitive landscape Markdown export."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from max.analysis.design_brief_competitive_landscape import SCHEMA_VERSION
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.server.app import create_app
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit
from max.types.evaluation import DimensionScore, UtilityEvaluation


def _unit(unit_id: str, title: str) -> BuildableUnit:
    return BuildableUnit(
        id=unit_id,
        title=title,
        one_liner="Export competitive landscape Markdown for design brief handoff",
        category="application",
        problem="Design brief reviewers need competitor context in a readable artifact.",
        solution="Render the existing competitive landscape report as Markdown.",
        value_proposition="Make competitive positioning easy to review and share.",
        specific_user="product engineer",
        buyer="product lead",
        workflow_context="design brief handoff",
        validation_plan="Review generated Markdown with source ideas and prior art.",
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
        overall_score=78.0,
        strengths=["handoff-ready"],
        weaknesses=["competition exists"],
        recommendation="yes",
        weights_used={"competitive_density": 0.1},
    )


@pytest.fixture
def competitive_landscape_markdown_db(tmp_path) -> tuple[str, str]:
    db_path = str(tmp_path / "competitive_landscape_markdown_api.db")
    store = Store(db_path=db_path, wal_mode=True)
    try:
        lead = _unit("bu-competitive-md-lead", "Competitive Markdown Lead")
        supporting = _unit("bu-competitive-md-supporting", "Competitive Markdown Supporting")
        for unit in (lead, supporting):
            store.insert_buildable_unit(unit)
            store.insert_evaluation(_evaluation(unit.id))
            store.insert_prior_art_match(
                unit.id,
                {
                    "source": "github",
                    "title": f"existing-{unit.id}-landscape",
                    "url": f"https://github.com/example/existing-{unit.id}-landscape",
                    "description": "Stored prior-art record for competitive landscape Markdown.",
                    "relevance_score": 0.86,
                    "match_signals": {"stars": 54},
                    "search_query": "design brief competitive landscape markdown",
                },
            )
            store.update_prior_art_status(unit.id, "weak_match")

        brief_id = store.insert_design_brief(
            ProjectBrief(
                title="Competitive Landscape Markdown Brief",
                domain="developer-tools",
                theme="competitive-handoff",
                lead=Candidate(unit=lead),
                supporting=[Candidate(unit=supporting)],
                readiness_score=84.0,
                why_this_now="Design briefs need positioning before implementation.",
                merged_product_concept="A deterministic competitive landscape Markdown export.",
                synthesis_rationale="Linked source ideas already have stored prior-art records.",
                mvp_scope=["Competitive landscape Markdown endpoint"],
                first_milestones=["Return Markdown through the API"],
                validation_plan="Call the API in implementation planning.",
                risks=["Competitor data may be sparse."],
                source_idea_ids=[lead.id, supporting.id],
            )
        )
    finally:
        store.close()
    return db_path, brief_id


@pytest.fixture
def competitive_landscape_markdown_client(
    competitive_landscape_markdown_db: tuple[str, str],
) -> tuple[TestClient, str]:
    from max.server.dependencies import get_store

    db_path, brief_id = competitive_landscape_markdown_db
    app = create_app()

    def override_get_store():
        store = Store(db_path=db_path, wal_mode=True)
        try:
            yield store
        finally:
            store.close()

    app.dependency_overrides[get_store] = override_get_store
    return TestClient(app), brief_id


def test_get_design_brief_competitive_landscape_markdown_export_success(
    competitive_landscape_markdown_client: tuple[TestClient, str],
) -> None:
    client, brief_id = competitive_landscape_markdown_client
    response = client.get(f"/api/v1/design-briefs/{brief_id}/competitive-landscape.md")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"] == (
        f'attachment; filename="{brief_id}-Competitive-Landscape-Markdown-Brief'
        '-competitive-landscape.md"'
    )
    assert response.text.startswith("# Competitive Landscape: Competitive Landscape Markdown Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in response.text
    assert "## Recommended Positioning" in response.text
    assert "## Open-source repository competitors" in response.text
    assert "existing-bu-competitive-md-lead-landscape" in response.text
    assert "Suggested response:" in response.text


def test_get_design_brief_competitive_landscape_markdown_missing_brief(
    competitive_landscape_markdown_client: tuple[TestClient, str],
) -> None:
    client, _brief_id = competitive_landscape_markdown_client
    response = client.get("/api/v1/design-briefs/dbf-missing/competitive-landscape.md")

    assert response.status_code == 404
    assert response.json()["detail"] == "Design brief not found: dbf-missing"
