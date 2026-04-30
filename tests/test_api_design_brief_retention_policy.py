"""API tests for design brief retention policy exports."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from max.analysis.design_brief_retention_policy import SCHEMA_VERSION
from max.server.app import create_app
from max.server.dependencies import get_store


class FakeStore:
    def __init__(self, briefs: dict[str, dict]):
        self._briefs = briefs

    def get_design_brief(self, brief_id: str) -> dict | None:
        return self._briefs.get(brief_id)


@pytest.fixture
def brief_id() -> str:
    return "dbf-retention-policy"


@pytest.fixture
def fake_store(brief_id: str) -> FakeStore:
    return FakeStore(
        {
            brief_id: {
                "id": brief_id,
                "title": "Retention Policy Brief",
                "domain": "customer-operations",
                "theme": "customer-data-handoff",
                "readiness_score": 82.0,
                "design_status": "approved",
                "lead_idea_id": "bu-retention-policy",
                "source_idea_ids": ["bu-retention-policy"],
                "created_at": "2026-04-25T10:00:00Z",
                "updated_at": "2026-04-26T11:00:00Z",
                "buyer": "operations director",
                "specific_user": "customer operations manager",
                "workflow_context": "customer onboarding audit handoff",
                "first_10_customers": "regulated customer success teams",
                "merged_product_concept": "Retention-aware design brief handoff.",
                "mvp_scope": ["Retention policy JSON", "Retention policy Markdown"],
                "validation_plan": "Confirm deletion owner and audit evidence before launch.",
                "risks": ["Customer data retention and audit ownership may be unclear."],
                "domain_risks": ["Privacy review required before telemetry collection."],
                "tech_approach": "Persist policy outputs with audit metadata.",
            }
        }
    )


@pytest.fixture
def client(fake_store: FakeStore) -> TestClient:
    app = create_app()

    def override_get_store():
        yield fake_store

    app.dependency_overrides[get_store] = override_get_store
    return TestClient(app)


def test_get_design_brief_retention_policy_json(
    client: TestClient,
    brief_id: str,
) -> None:
    response = client.get(f"/api/v1/design-briefs/{brief_id}/retention-policy")

    assert response.status_code == 200
    data = response.json()
    assert data["schema_version"] == SCHEMA_VERSION
    assert data["kind"] == "max.design_brief.retention_policy"
    assert data["source"]["id"] == brief_id
    assert data["source"]["generated_at"] == "2026-04-26T11:00:00Z"
    assert data["design_brief"]["id"] == brief_id
    assert data["design_brief"]["title"] == "Retention Policy Brief"
    assert data["summary"]["data_class_count"] >= 3
    assert data["summary"]["retention_rule_count"] == len(data["retention_rules"])
    assert {item["id"] for item in data["data_classes"]} >= {
        "design_brief_record",
        "evidence_references",
        "stakeholder_context",
        "sensitive_operational_data",
    }
    assert data["retention_rules"][0]["retention_period"]
    assert data["deletion_controls"]
    assert data["audit_requirements"]


def test_get_design_brief_retention_policy_markdown_download(
    client: TestClient,
    brief_id: str,
) -> None:
    response = client.get(f"/api/v1/design-briefs/{brief_id}/retention-policy.md")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"] == (
        f'attachment; filename="{brief_id}-retention-policy.md"'
    )
    assert response.text.startswith("# Retention Policy: Retention Policy Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in response.text
    assert f"Design brief: `{brief_id}`" in response.text
    assert "## Data Classes" in response.text
    assert "## Retention Rules" in response.text
    assert "## Deletion Controls" in response.text
    assert "## Audit Requirements" in response.text


def test_get_design_brief_retention_policy_missing_brief_returns_404(
    client: TestClient,
) -> None:
    json_response = client.get("/api/v1/design-briefs/dbf-missing/retention-policy")
    markdown_response = client.get("/api/v1/design-briefs/dbf-missing/retention-policy.md")

    assert json_response.status_code == 404
    assert json_response.json()["detail"] == "Design brief not found: dbf-missing"
    assert markdown_response.status_code == 404
    assert markdown_response.json()["detail"] == "Design brief not found: dbf-missing"
