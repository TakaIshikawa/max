from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from max.analysis.design_brief_roadmap import (
    SCHEMA_VERSION,
    build_design_brief_roadmap,
    render_design_brief_roadmap,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.server.app import create_app
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


def _unit(
    unit_id: str,
    *,
    title: str,
    solution: str,
    domain_risks: list[str],
) -> BuildableUnit:
    return BuildableUnit(
        id=unit_id,
        title=title,
        one_liner="Roadmap source idea",
        category="application",
        problem="Planning teams need design briefs to become actionable.",
        solution=solution,
        value_proposition="Turn design context into delegated work.",
        specific_user="product engineer",
        buyer="engineering manager",
        workflow_context="design handoff planning",
        current_workaround="manual project planning",
        why_now="Design briefs are persisted and ready for downstream planning.",
        validation_plan="Interview planning leads and run a smoke test.",
        domain_risks=domain_risks,
        tech_approach="Python API with deterministic analysis.",
        suggested_stack={"language": "python"},
        domain="developer-tools",
        status="approved",
    )


def _seed_brief(store: Store) -> str:
    lead = _unit(
        "bu-roadmap-lead",
        title="Roadmap Lead Idea",
        solution="Generate phased work plans from design briefs.",
        domain_risks=["Planner adoption may be weak without owner assignments."],
    )
    support = _unit(
        "bu-roadmap-support",
        title="Roadmap Support Idea",
        solution="Trace roadmap work back to source ideas.",
        domain_risks=["API integration details may change during implementation."],
    )
    store.insert_buildable_unit(lead)
    store.insert_buildable_unit(support)
    return store.insert_design_brief(
        ProjectBrief(
            title="Roadmap Brief",
            domain="developer-tools",
            theme="handoff-planning",
            lead=Candidate(unit=lead),
            supporting=[Candidate(unit=support)],
            readiness_score=84.0,
            why_this_now="Teams need design briefs to become actionable plans.",
            merged_product_concept="A deterministic roadmap generator for design briefs.",
            synthesis_rationale="Combines planning and source traceability ideas.",
            mvp_scope=["Roadmap API", "MCP roadmap resource"],
            first_milestones=["Generate roadmap phases", "Compare REST and MCP outputs"],
            validation_plan="Validate roadmap usefulness with product and engineering leads.",
            risks=["Roadmap quality may be too generic for delegation."],
            source_idea_ids=["bu-roadmap-lead", "bu-roadmap-support"],
        )
    )


def test_build_design_brief_roadmap_generates_required_phases_and_items(tmp_path) -> None:
    store = Store(str(tmp_path / "max.db"))
    try:
        brief_id = _seed_brief(store)
        roadmap = build_design_brief_roadmap(store, brief_id)
    finally:
        store.close()

    assert roadmap is not None
    assert roadmap["schema_version"] == SCHEMA_VERSION
    assert [phase["id"] for phase in roadmap["phases"]] == [
        "discovery",
        "prototype",
        "validation",
        "beta",
        "launch",
    ]
    assert all(phase["items"] for phase in roadmap["phases"])
    assert all(
        {
            "id",
            "phase",
            "title",
            "rationale",
            "owner_role",
            "dependency_ids",
            "exit_criteria",
            "source_idea_ids",
        }
        <= set(item)
        for item in roadmap["items"]
    )


def test_build_design_brief_roadmap_keeps_source_traceability(tmp_path) -> None:
    store = Store(str(tmp_path / "max.db"))
    try:
        brief_id = _seed_brief(store)
        roadmap = build_design_brief_roadmap(store, brief_id)
    finally:
        store.close()

    assert roadmap is not None
    item_sources = [set(item["source_idea_ids"]) for item in roadmap["items"]]
    assert {"bu-roadmap-lead"} in item_sources
    assert any("bu-roadmap-support" in sources for sources in item_sources)
    assert all(isinstance(item["dependency_ids"], list) for item in roadmap["items"])
    assert all(item["exit_criteria"] for item in roadmap["items"])


def test_build_design_brief_roadmap_missing_brief_returns_none(tmp_path) -> None:
    store = Store(str(tmp_path / "max.db"))
    try:
        assert build_design_brief_roadmap(store, "dbf-missing") is None
    finally:
        store.close()


def test_render_design_brief_roadmap_json_and_markdown(tmp_path) -> None:
    store = Store(str(tmp_path / "max.db"))
    try:
        brief_id = _seed_brief(store)
        roadmap = build_design_brief_roadmap(store, brief_id)
    finally:
        store.close()

    assert roadmap is not None
    parsed = json.loads(render_design_brief_roadmap(roadmap, "json"))
    assert parsed["schema_version"] == SCHEMA_VERSION

    markdown = render_design_brief_roadmap(roadmap, "markdown")
    assert markdown.startswith("# Roadmap: Roadmap Brief")
    assert "Schema: `max.design_brief.roadmap.v1`" in markdown
    assert "## Discovery" in markdown

    with pytest.raises(ValueError):
        render_design_brief_roadmap(roadmap, "yaml")


@pytest.fixture
def roadmap_client(tmp_path):
    db_path = str(tmp_path / "api.db")
    store = Store(db_path=db_path, wal_mode=True)
    brief_id = _seed_brief(store)
    store.close()

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


def test_get_design_brief_roadmap_rest_response(roadmap_client) -> None:
    client, brief_id = roadmap_client
    response = client.get(f"/api/v1/design-briefs/{brief_id}/roadmap")

    assert response.status_code == 200
    data = response.json()
    assert data["schema_version"] == SCHEMA_VERSION
    assert data["design_brief"]["id"] == brief_id
    assert [phase["id"] for phase in data["phases"]] == [
        "discovery",
        "prototype",
        "validation",
        "beta",
        "launch",
    ]


def test_get_design_brief_roadmap_rest_not_found(roadmap_client) -> None:
    client, _brief_id = roadmap_client
    response = client.get("/api/v1/design-briefs/dbf-missing/roadmap")

    assert response.status_code == 404
    assert response.json()["detail"] == "Design brief not found: dbf-missing"
