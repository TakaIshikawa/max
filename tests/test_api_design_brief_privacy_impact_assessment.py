"""REST tests for design brief privacy impact assessment exports."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from max.analysis.design_brief_privacy_impact_assessment import SCHEMA_VERSION
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.server.app import create_app
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


@pytest.fixture
def client(tmp_path) -> TestClient:
    db_path = str(tmp_path / "privacy_impact_assessment_api.db")
    store = Store(db_path=db_path, wal_mode=True)
    store.close()

    from max.server.dependencies import get_store

    app = create_app()
    app.state.test_db_path = db_path

    def override_get_store():
        request_store = Store(db_path=db_path, wal_mode=True)
        try:
            yield request_store
        finally:
            request_store.close()

    app.dependency_overrides[get_store] = override_get_store
    return TestClient(app)


def test_get_design_brief_privacy_impact_assessment_returns_json(client: TestClient) -> None:
    db_path = _client_db_path(client)
    brief_id = _seed_privacy_brief(db_path)

    response = client.get(f"/api/v1/design-briefs/{brief_id}/privacy-impact-assessment")

    assert response.status_code == 200
    data = response.json()
    assert data["schema_version"] == SCHEMA_VERSION
    assert data["kind"] == "max.design_brief.privacy_impact_assessment"
    assert data["design_brief"]["id"] == brief_id
    assert data["summary"]["privacy_gate"] == "privacy_review_required"
    assert data["summary"]["sensitive_data_expected"] is True
    assert "regulated_sensitive_data" in [category["id"] for category in data["data_categories"]]
    assert data["processing_purposes"][0]["id"] == "core_workflow_delivery"


def test_get_design_brief_privacy_impact_assessment_returns_markdown(client: TestClient) -> None:
    db_path = _client_db_path(client)
    brief_id = _seed_privacy_brief(db_path)

    response = client.get(f"/api/v1/design-briefs/{brief_id}/privacy-impact-assessment?format=markdown")
    markdown_response = client.get(f"/api/v1/design-briefs/{brief_id}/privacy-impact-assessment.md")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.text == markdown_response.text
    assert response.text.startswith("# Privacy Impact Assessment: API Privacy Brief")
    assert f"Design brief: `{brief_id}`" in response.text
    assert "## Privacy Risks" in response.text


def test_get_design_brief_privacy_impact_assessment_missing_brief(client: TestClient) -> None:
    response = client.get("/api/v1/design-briefs/dbf-missing/privacy-impact-assessment")
    markdown_response = client.get("/api/v1/design-briefs/dbf-missing/privacy-impact-assessment.md")

    assert response.status_code == 404
    assert response.json()["detail"] == "Design brief not found: dbf-missing"
    assert markdown_response.status_code == 404


def test_design_brief_privacy_impact_assessment_openapi_schema(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()

    assert "DesignBriefPrivacyImpactAssessmentResponse" in schema["components"]["schemas"]
    operation = schema["paths"]["/api/v1/design-briefs/{brief_id}/privacy-impact-assessment"]["get"]
    assert operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/DesignBriefPrivacyImpactAssessmentResponse"
    )
    assert any(param["name"] == "format" for param in operation["parameters"])


def _client_db_path(client: TestClient) -> str:
    return str(client.app.state.test_db_path)


def _seed_privacy_brief(db_path: str) -> str:
    store = Store(db_path=db_path, wal_mode=True)
    try:
        unit = BuildableUnit(
            id="bu-api-privacy",
            title="API Privacy Idea",
            one_liner="Expose privacy impact assessments over REST.",
            category="application",
            problem="Healthcare buyers need privacy review before pilot launch.",
            solution="Serve deterministic privacy impact assessment artifacts from persisted briefs.",
            value_proposition="Reduce launch risk for regulated workflow automation.",
            specific_user="care coordinator",
            buyer="hospital compliance lead",
            workflow_context="patient discharge planning workflow with clinical notes",
            validation_plan="Run discovery with synthetic patient examples.",
            evidence_signals=["sig-api-privacy"],
            inspiring_insights=["ins-api-privacy"],
            domain_risks=["Patient data may include HIPAA-regulated PII."],
            tech_approach="Python API with EHR integration and audit logs.",
            suggested_stack={"language": "python", "integration": "EHR API"},
            domain="healthcare",
            status="approved",
        )
        store.insert_buildable_unit(unit)
        return store.insert_design_brief(
            ProjectBrief(
                title="API Privacy Brief",
                domain="healthcare",
                theme="privacy-impact-assessment",
                lead=Candidate(unit=unit),
                readiness_score=82.0,
                why_this_now="Care teams need privacy-safe automation now.",
                merged_product_concept="Coordinate discharge handoffs using patient records and generated summaries.",
                synthesis_rationale="Regulated healthcare workflow needs privacy assessment.",
                mvp_scope=["Patient handoff summary", "Audit log export", "EHR API integration"],
                first_milestones=["Map data flow", "Implement role-based access"],
                validation_plan="Run pilot with synthetic patient data before real records.",
                risks=["Patient data may include PII and requires privacy review."],
                source_idea_ids=[unit.id],
                design_status="approved",
            )
        )
    finally:
        store.close()
