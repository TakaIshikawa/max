"""Tests for design brief failure mode REST exports."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from max.analysis.design_brief_failure_modes import SCHEMA_VERSION
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.server.app import create_app
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


@pytest.fixture
def db_path(tmp_path) -> str:
    path = str(tmp_path / "test_design_brief_failure_modes_api.db")
    Store(db_path=path, wal_mode=True).close()
    return path


@pytest.fixture
def client(db_path: str) -> TestClient:
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
def seeded_brief_id(db_path: str) -> str:
    store = Store(db_path=db_path, wal_mode=True)
    try:
        lead = BuildableUnit(
            id="bu-failure-api-lead",
            title="Failure Modes API Lead",
            one_liner="Expose failure modes before implementation handoff.",
            category="application",
            problem="Automation clients cannot fetch failure mode analysis over REST.",
            solution="Publish deterministic failure modes for persisted design briefs.",
            value_proposition="Make implementation risks visible to dashboards and agents.",
            specific_user="implementation agent",
            buyer="VP of Product",
            workflow_context="pre-build launch review",
            current_workaround="manual risk review checklist",
            why_now="Design brief artifacts are already deterministic.",
            validation_plan="Run a launch review with risk owners and require pass/fail decisions.",
            first_10_customers="product teams turning design briefs into implementation tasks",
            domain_risks=["Security review may block pilot launch."],
            evidence_signals=[],
            tech_approach="FastAPI endpoint over deterministic FMEA generation.",
            suggested_stack={"language": "python", "framework": "fastapi"},
            domain="developer-tools",
            status="approved",
        )
        support = BuildableUnit(
            id="bu-failure-api-support",
            title="Failure Modes API Support",
            one_liner="Attach mitigation and detection detail to failure modes.",
            category="application",
            problem="Failure analysis needs owners, detection methods, and mitigations.",
            solution="Rank failure modes and return structured mitigation guidance.",
            value_proposition="Reduce preventable launch and validation misses.",
            specific_user="product engineer",
            buyer="engineering director",
            workflow_context="implementation readiness review",
            current_workaround="spreadsheet risk register",
            domain_risks=["Legacy API sync can drop review state."],
            evidence_signals=[],
            tech_approach="Deterministic scoring with persisted source idea context.",
            domain="developer-tools",
            status="approved",
        )
        store.insert_buildable_unit(lead)
        store.insert_buildable_unit(support)
        return store.insert_design_brief(
            ProjectBrief(
                title="Failure Modes API Brief",
                domain="developer-tools",
                theme="failure-modes",
                lead=Candidate(unit=lead),
                supporting=[Candidate(unit=support)],
                readiness_score=76.0,
                why_this_now="Agents need failure analysis before implementation handoff.",
                merged_product_concept="A failure modes artifact for persisted design briefs.",
                synthesis_rationale="Extends design briefs with risk priority and mitigation detail.",
                mvp_scope=["Failure modes JSON endpoint", "Markdown failure modes export"],
                first_milestones=["Return sorted FMEA report over REST"],
                validation_plan=(
                    "Run a launch review with risk owners and require pass/fail decisions."
                ),
                risks=[
                    "Security review may block pilot launch.",
                    "Legacy API sync can drop review state.",
                    "Buyer adoption may stall after initial validation.",
                ],
                source_idea_ids=[lead.id, support.id],
                design_status="approved",
            )
        )
    finally:
        store.close()


def test_get_design_brief_failure_modes_json(
    client: TestClient,
    seeded_brief_id: str,
) -> None:
    response = client.get(f"/api/v1/design-briefs/{seeded_brief_id}/failure-modes")

    assert response.status_code == 200
    data = response.json()
    assert data["schema_version"] == SCHEMA_VERSION
    assert data["kind"] == "max.design_brief.failure_modes"
    assert data["design_brief"]["id"] == seeded_brief_id
    assert data["design_brief"]["title"] == "Failure Modes API Brief"
    assert data["summary"]["failure_mode_count"] == len(data["failure_modes"])
    assert data["failure_modes"][0]["risk_priority_number"] >= data["failure_modes"][-1][
        "risk_priority_number"
    ]
    assert any(
        "Security review may block pilot launch" in mode["failure_mode"]
        for mode in data["failure_modes"]
    )


def test_get_design_brief_failure_modes_markdown_download(
    client: TestClient,
    seeded_brief_id: str,
) -> None:
    response = client.get(f"/api/v1/design-briefs/{seeded_brief_id}/failure-modes.md")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"] == (
        f'attachment; filename="{seeded_brief_id}-Failure-Modes-API-Brief-failure-modes.md"'
    )
    assert response.text.startswith("# Failure Modes: Failure Modes API Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in response.text
    assert f"Design brief: `{seeded_brief_id}`" in response.text
    assert "## Prioritized Failure Modes" in response.text
    assert "Detection method:" in response.text
    assert "Mitigation:" in response.text


def test_get_design_brief_failure_modes_missing_brief_returns_404(
    client: TestClient,
) -> None:
    json_response = client.get("/api/v1/design-briefs/dbf-missing/failure-modes")
    markdown_response = client.get("/api/v1/design-briefs/dbf-missing/failure-modes.md")

    assert json_response.status_code == 404
    assert json_response.json()["detail"] == "Design brief not found: dbf-missing"
    assert markdown_response.status_code == 404
    assert markdown_response.json()["detail"] == "Design brief not found: dbf-missing"
