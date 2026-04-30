"""API tests for design brief compliance checklist exports."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.server.app import create_app
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit
from max.types.signal import Signal, SignalSourceType


@pytest.fixture
def compliance_checklist_db(tmp_path) -> tuple[str, str]:
    db_path = str(tmp_path / "design_brief_compliance_checklist_api.db")
    store = Store(db_path=db_path, wal_mode=True)
    try:
        store.insert_signal(
            Signal(
                id="sig-api-security",
                source_type=SignalSourceType.SECURITY,
                source_adapter="security_feed",
                title="Security launch risk",
                content="Launch governance needs security review.",
                url="https://example.com/sig-api-security",
                tags=["security", "launch"],
                metadata={"signal_role": "risk"},
            )
        )
        lead = BuildableUnit(
            id="bu-compliance-api-lead",
            title="Compliance API Lead",
            one_liner="Expose compliance checklist from design briefs.",
            category="application",
            problem="Execution handoffs need compliance gates.",
            solution="Add design brief compliance checklist endpoints.",
            value_proposition="Give implementers a deterministic compliance checklist.",
            specific_user="implementation lead",
            buyer="engineering manager",
            workflow_context="release planning with customer data",
            current_workaround="manual compliance docs",
            why_now="Design brief handoff exports already exist.",
            validation_plan="Fetch JSON and Markdown compliance checklist endpoints.",
            first_10_customers="internal implementation leads",
            domain_risks=["Security review may be skipped before launch."],
            evidence_signals=["sig-api-security"],
            tech_approach="FastAPI route and deterministic builder.",
            suggested_stack={"language": "python"},
            domain="developer-tools",
            status="approved",
        )
        store.insert_buildable_unit(lead)
        brief_id = store.insert_design_brief(
            ProjectBrief(
                title="Compliance Checklist API Brief",
                domain="developer-tools",
                theme="compliance-export",
                lead=Candidate(unit=lead),
                supporting=[],
                readiness_score=84.0,
                why_this_now="Compliance review is needed before execution.",
                merged_product_concept="Design brief compliance checklist export.",
                synthesis_rationale="Completes the handoff artifact set.",
                mvp_scope=["Compliance checklist JSON", "Compliance checklist Markdown"],
                first_milestones=["Return typed JSON", "Return downloadable Markdown"],
                validation_plan="Compare JSON sections with Markdown headings.",
                risks=["Checklist may omit governance ownership."],
                source_idea_ids=[lead.id],
                design_status="approved",
            )
        )
    finally:
        store.close()
    return db_path, brief_id


@pytest.fixture
def compliance_checklist_client(
    compliance_checklist_db: tuple[str, str],
) -> tuple[TestClient, str]:
    from max.server.dependencies import get_store

    db_path, brief_id = compliance_checklist_db
    app = create_app()

    def override_get_store():
        store = Store(db_path=db_path, wal_mode=True)
        try:
            yield store
        finally:
            store.close()

    app.dependency_overrides[get_store] = override_get_store
    return TestClient(app), brief_id


def test_get_design_brief_compliance_checklist_json_success(
    compliance_checklist_client: tuple[TestClient, str],
) -> None:
    client, brief_id = compliance_checklist_client
    response = client.get(f"/api/v1/design-briefs/{brief_id}/compliance-checklist")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == "max.design_brief.compliance_checklist.v1"
    assert payload["kind"] == "max.design_brief.compliance_checklist"
    assert payload["design_brief"]["id"] == brief_id
    assert payload["summary"]["gate"] == "ready_for_compliance_review"
    assert [section["id"] for section in payload["sections"]] == [
        "security",
        "privacy",
        "accessibility",
        "data_retention",
        "launch_governance",
    ]
    assert payload["checklist_items"][0]["section_id"] == "security"
    assert payload["checklist_items"][0]["source_idea_ids"] == ["bu-compliance-api-lead"]
    assert any(ref["id"] == "sig-api-security" for ref in payload["evidence_references"])
    assert payload["recommended_next_actions"]


def test_get_design_brief_compliance_checklist_markdown_success(
    compliance_checklist_client: tuple[TestClient, str],
) -> None:
    client, brief_id = compliance_checklist_client
    response = client.get(f"/api/v1/design-briefs/{brief_id}/compliance-checklist.md")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"] == (
        f'attachment; filename="{brief_id}-Compliance-Checklist-API-Brief-compliance-checklist.md"'
    )
    assert response.text.startswith("# Compliance Checklist: Compliance Checklist API Brief")
    assert "## Security" in response.text
    assert "## Privacy" in response.text
    assert "## Accessibility" in response.text
    assert "## Data Retention" in response.text
    assert "## Launch Governance" in response.text


def test_get_design_brief_compliance_checklist_markdown_headings_match_json(
    compliance_checklist_client: tuple[TestClient, str],
) -> None:
    client, brief_id = compliance_checklist_client
    json_response = client.get(f"/api/v1/design-briefs/{brief_id}/compliance-checklist")
    markdown_response = client.get(f"/api/v1/design-briefs/{brief_id}/compliance-checklist.md")

    assert json_response.status_code == 200
    assert markdown_response.status_code == 200
    section_headings = [
        line.removeprefix("## ")
        for line in markdown_response.text.splitlines()
        if line.startswith("## ") and line != "## Recommended Next Actions"
    ]
    assert section_headings == [section["title"] for section in json_response.json()["sections"]]


def test_get_design_brief_compliance_checklist_json_missing_brief(
    compliance_checklist_client: tuple[TestClient, str],
) -> None:
    client, _brief_id = compliance_checklist_client
    response = client.get("/api/v1/design-briefs/dbf-missing/compliance-checklist")

    assert response.status_code == 404
    assert response.json()["detail"] == "Design brief not found: dbf-missing"


def test_get_design_brief_compliance_checklist_markdown_missing_brief(
    compliance_checklist_client: tuple[TestClient, str],
) -> None:
    client, _brief_id = compliance_checklist_client
    response = client.get("/api/v1/design-briefs/dbf-missing/compliance-checklist.md")

    assert response.status_code == 404
    assert response.json()["detail"] == "Design brief not found: dbf-missing"
