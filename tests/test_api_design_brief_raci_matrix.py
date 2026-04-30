"""Tests for design brief RACI matrix REST exports."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from max.analysis.design_brief_raci_matrix import SCHEMA_VERSION
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.server.app import create_app
from max.server.dependencies import get_store
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


@pytest.fixture
def db_path(tmp_path) -> str:
    path = str(tmp_path / "test_design_brief_raci_matrix_api.db")
    Store(db_path=path, wal_mode=True).close()
    return path


@pytest.fixture
def client(db_path: str) -> TestClient:
    app = create_app()

    def override_get_store():
        store = Store(db_path=db_path, wal_mode=True)
        try:
            yield store
        finally:
            store.close()

    app.dependency_overrides[get_store] = override_get_store
    return TestClient(app)


def _seed_design_brief(db_path: str) -> str:
    store = Store(db_path=db_path, wal_mode=True)
    try:
        lead = BuildableUnit(
            id="bu-raci-api-lead",
            title="RACI Matrix API Lead",
            one_liner="Prepare RACI handoffs from design briefs.",
            category="application",
            problem="Implementation agents and project managers need ownership clarity.",
            solution="Export deterministic RACI matrices from persisted design briefs.",
            value_proposition="Reduce launch handoff ambiguity for organizational buyers.",
            specific_user="implementation manager",
            buyer="VP of Operations",
            workflow_context="enterprise workflow rollout with customer data",
            current_workaround="manual handoff docs",
            why_now="Design briefs increasingly support implementation handoffs.",
            validation_plan="Run RACI review with two pilot implementation managers.",
            first_10_customers="mid-market operations teams with formal launch playbooks",
            domain_risks=[
                "Security and privacy review may delay customer data access.",
                "Support ownership may be unclear after pilot launch.",
            ],
            evidence_rationale="Signals show ownership, support, and launch readiness gaps.",
            evidence_signals=[],
            inspiring_insights=[],
            tech_approach="FastAPI and persisted RACI generation with audit-friendly JSON.",
            suggested_stack={"language": "python", "framework": "fastapi"},
            composability_notes="Create a reusable project-manager playbook export.",
            domain="developer-tools",
            status="approved",
        )
        support = BuildableUnit(
            id="bu-raci-api-support",
            title="RACI Matrix API Support",
            one_liner="Support launch handoff playbooks.",
            category="automation",
            problem="Support teams need playbooks before rollout.",
            solution="Attach playbook responsibilities to RACI rows.",
            value_proposition="Make support ownership explicit.",
            specific_user="support operations lead",
            buyer="VP of Operations",
            workflow_context="pilot support workflow",
            current_workaround="ad hoc support notes",
            validation_plan="Test support escalation during pilot.",
            first_10_customers="operations teams with shared support queues",
            domain_risks=["Launch support can miss escalation coverage."],
            evidence_rationale="Support gaps appear during pilot handoffs.",
            tech_approach="Generate support playbook rows.",
            composability_notes="Playbook template for support and rollout ownership.",
            domain="developer-tools",
            status="approved",
        )
        store.insert_buildable_unit(lead)
        store.insert_buildable_unit(support)
        return store.insert_design_brief(
            ProjectBrief(
                title="RACI Matrix Brief",
                domain="developer-tools",
                theme="handoff-ownership",
                lead=Candidate(unit=lead),
                supporting=[Candidate(unit=support)],
                readiness_score=88.0,
                why_this_now="Design briefs increasingly support handoff workflows.",
                merged_product_concept="A RACI matrix export for persisted design briefs.",
                synthesis_rationale=(
                    "Connects buyer, user, implementation, support, risk, and launch ownership."
                ),
                mvp_scope=["JSON RACI matrix", "Markdown RACI matrix"],
                first_milestones=["Return RACI matrix JSON", "Render grouped Markdown table"],
                validation_plan="Confirm RACI traceability with implementation and budget owners.",
                risks=["Legal review is required before customer workflow data is used."],
                source_idea_ids=[lead.id, support.id],
                design_status="approved",
            )
        )
    finally:
        store.close()


def test_get_design_brief_raci_matrix_json(
    client: TestClient,
    db_path: str,
) -> None:
    brief_id = _seed_design_brief(db_path)

    response = client.get(f"/api/v1/design-briefs/{brief_id}/raci-matrix")

    assert response.status_code == 200
    data = response.json()
    assert data["schema_version"] == SCHEMA_VERSION
    assert data["kind"] == "max.design_brief.raci_matrix"
    assert data["design_brief"]["id"] == brief_id
    assert data["design_brief"]["title"] == "RACI Matrix Brief"
    assert data["design_brief"]["buyer"] == "VP of Operations"
    assert data["summary"]["activity_count"] == 8
    assert data["summary"]["role_count"] == 6
    assert [phase["id"] for phase in data["phases"]] == [
        "alignment",
        "implementation_handoff",
        "validation",
        "launch_readiness",
    ]
    assert data["activities"][0]["id"] == "DBRACI1"
    assert data["activities"][0]["accountable_role"] == "VP of Operations"
    assert data["activities"][4]["responsible_role"] == "implementation manager"
    assert any(
        assignment["role"] == "Support/playbook owner"
        and assignment["responsible_activity_ids"] == ["DBRACI4", "DBRACI8"]
        for assignment in data["role_assignments"]
    )


def test_get_design_brief_raci_matrix_markdown_download(
    client: TestClient,
    db_path: str,
) -> None:
    brief_id = _seed_design_brief(db_path)

    response = client.get(f"/api/v1/design-briefs/{brief_id}/raci-matrix.md")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"] == (
        f'attachment; filename="{brief_id}-RACI-Matrix-Brief-raci-matrix.md"'
    )
    assert response.text.startswith("# RACI Matrix: RACI Matrix Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in response.text
    assert f"Design brief: `{brief_id}`" in response.text
    assert "## Alignment" in response.text
    assert "## Implementation Handoff" in response.text
    assert "| Activity | Responsible | Accountable | Consulted | Informed | Gaps |" in response.text


def test_get_design_brief_raci_matrix_missing_brief_returns_404(
    client: TestClient,
) -> None:
    json_response = client.get("/api/v1/design-briefs/dbf-missing/raci-matrix")
    markdown_response = client.get("/api/v1/design-briefs/dbf-missing/raci-matrix.md")

    assert json_response.status_code == 404
    assert json_response.json()["detail"] == "Design brief not found: dbf-missing"
    assert markdown_response.status_code == 404
    assert markdown_response.json()["detail"] == "Design brief not found: dbf-missing"
