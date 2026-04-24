"""API tests for design brief evidence matrix Markdown export."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.server.app import create_app
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit
from max.types.insight import Insight, InsightCategory
from max.types.signal import Signal, SignalSourceType


@pytest.fixture
def evidence_matrix_markdown_db(tmp_path) -> tuple[str, str]:
    db_path = str(tmp_path / "evidence_matrix_markdown_api.db")
    store = Store(db_path=db_path, wal_mode=True)
    try:
        signal = Signal(
            id="sig-evidence-md-problem",
            source_type=SignalSourceType.FORUM,
            source_adapter="test",
            title="Problem evidence",
            content="Teams need readable evidence matrix handoffs.",
            url="https://example.com/sig-evidence-md-problem",
            tags=["problem"],
            credibility=0.8,
            metadata={"signal_role": "problem"},
        )
        store.insert_signal(signal)
        store.insert_insight(
            Insight(
                id="ins-evidence-md-gap",
                category=InsightCategory.GAP,
                title="Evidence handoff gap",
                summary="Reviewers need evidence matrices outside JSON.",
                evidence=[signal.id],
                confidence=0.8,
                domains=["developer-tools"],
            )
        )
        lead = BuildableUnit(
            id="bu-evidence-md-lead",
            title="Evidence Matrix Markdown Lead",
            one_liner="Export design brief evidence matrices as Markdown",
            category="application",
            problem="Handoff workflows need a readable evidence artifact.",
            solution="Generate evidence matrix Markdown from persisted design briefs.",
            value_proposition="Give teams a deterministic evidence review artifact.",
            specific_user="product engineer",
            buyer="engineering manager",
            workflow_context="design evidence review",
            current_workaround="manual evidence notes",
            why_now="Persisted design briefs already expose evidence matrix JSON.",
            validation_plan="Review evidence matrix Markdown with product and engineering leads.",
            domain_risks=["Markdown exports may drift from JSON evidence matrix behavior."],
            evidence_rationale="Signals show evidence handoff gaps.",
            inspiring_insights=["ins-evidence-md-gap"],
            evidence_signals=[signal.id],
            tech_approach="FastAPI route using the evidence matrix renderer.",
            suggested_stack={"language": "python"},
            domain="developer-tools",
            status="approved",
        )
        store.insert_buildable_unit(lead)
        brief_id = store.insert_design_brief(
            ProjectBrief(
                title="Evidence Matrix Markdown Brief",
                domain="developer-tools",
                theme="handoff-export",
                lead=Candidate(unit=lead),
                supporting=[],
                readiness_score=82.0,
                why_this_now="Teams need a human-readable evidence matrix export.",
                merged_product_concept="A direct Markdown export for design brief evidence matrices.",
                synthesis_rationale="Completes the artifact surface for evidence handoffs.",
                mvp_scope=["Markdown evidence matrix export"],
                first_milestones=["Return evidence matrix Markdown from the API"],
                validation_plan="Confirm the response matches the evidence matrix renderer.",
                risks=["Markdown exports may drift from JSON evidence matrix behavior."],
                source_idea_ids=[lead.id],
            )
        )
    finally:
        store.close()
    return db_path, brief_id


@pytest.fixture
def evidence_matrix_markdown_client(
    evidence_matrix_markdown_db: tuple[str, str],
) -> tuple[TestClient, str]:
    from max.server.dependencies import get_store

    db_path, brief_id = evidence_matrix_markdown_db
    app = create_app()

    def override_get_store():
        store = Store(db_path=db_path, wal_mode=True)
        try:
            yield store
        finally:
            store.close()

    app.dependency_overrides[get_store] = override_get_store
    return TestClient(app), brief_id


def test_get_design_brief_evidence_matrix_markdown_export_success(
    evidence_matrix_markdown_client: tuple[TestClient, str],
) -> None:
    client, brief_id = evidence_matrix_markdown_client
    response = client.get(f"/api/v1/design-briefs/{brief_id}/evidence-matrix.md")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"] == (
        f'attachment; filename="{brief_id}-evidence-matrix.md"'
    )
    assert response.text.startswith("# Evidence Matrix: Evidence Matrix Markdown Brief")
    for claim_area in [
        "problem",
        "buyer",
        "workflow",
        "why_now",
        "validation_plan",
        "risks",
        "first_milestones",
    ]:
        assert f"## {claim_area}" in response.text
    assert "- **Evidence strength**:" in response.text
    assert "- **Supporting signals**: `sig-evidence-md-problem`" in response.text
    assert "- **Supporting insights**: `ins-evidence-md-gap`" in response.text
    assert "### Gaps" in response.text
    assert "### Validation Actions" in response.text


def test_get_design_brief_evidence_matrix_markdown_missing_brief(
    evidence_matrix_markdown_client: tuple[TestClient, str],
) -> None:
    client, _brief_id = evidence_matrix_markdown_client
    response = client.get("/api/v1/design-briefs/dbf-missing/evidence-matrix.md")

    assert response.status_code == 404
    assert response.json()["detail"] == "Design brief not found: dbf-missing"
