"""API tests for design brief one-pager exports."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from max.analysis.design_brief_one_pager import SCHEMA_VERSION
from max.server.app import create_app
from tests.test_design_brief_one_pager import InMemoryDesignBriefStore, one_pager_store


@pytest.fixture
def one_pager_client(
    one_pager_store: tuple[InMemoryDesignBriefStore, str],
) -> tuple[TestClient, str]:
    from max.server.dependencies import get_store

    store, brief_id = one_pager_store
    app = create_app()

    def override_get_store():
        yield store

    app.dependency_overrides[get_store] = override_get_store
    return TestClient(app), brief_id


def test_get_design_brief_one_pager_structured_response(
    one_pager_client: tuple[TestClient, str],
) -> None:
    client, brief_id = one_pager_client
    response = client.get(f"/api/v1/design-briefs/{brief_id}/one-pager")

    assert response.status_code == 200
    data = response.json()
    assert data["schema_version"] == SCHEMA_VERSION
    assert data["design_brief"]["id"] == brief_id
    assert data["title"] == "One-Pager Brief"
    assert data["domain"] == "developer-tools"
    assert data["target_customer"] == (
        "Primary user: portfolio reviewer. Buyer or sponsor: VP product."
    )
    assert data["problem"] == "Reviewers need a compact decision artifact."
    assert data["solution"] == "A deterministic one-page design brief summary."
    assert data["evidence_count"] >= 4
    assert data["readiness_score"] == 84.0
    assert data["top_risks"][0]["title"] == "Owner alignment may be unclear"
    assert data["validation_next_step"]
    assert data["first_milestone"] == "Expose one-pager REST export"
    assert data["source_idea_ids"] == ["bu-one-lead"]


def test_get_design_brief_one_pager_markdown_export_success(
    one_pager_client: tuple[TestClient, str],
) -> None:
    client, brief_id = one_pager_client
    response = client.get(f"/api/v1/design-briefs/{brief_id}/one-pager.md")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"] == (
        f'attachment; filename="{brief_id}-one-pager.md"'
    )
    assert response.text.startswith("# One-Pager: One-Pager Brief")
    assert "## Decision Fields" in response.text
    assert "**Problem**: Reviewers need a compact decision artifact." in response.text
    assert "**First milestone**: Expose one-pager REST export" in response.text
    assert "**Source idea IDs**: bu-one-lead" in response.text
    assert "## Top Risks" in response.text
    assert "{'" not in response.text
    assert "['" not in response.text


def test_get_design_brief_one_pager_missing_brief(
    one_pager_client: tuple[TestClient, str],
) -> None:
    client, _brief_id = one_pager_client

    json_response = client.get("/api/v1/design-briefs/dbf-missing/one-pager")
    assert json_response.status_code == 404
    assert json_response.json()["detail"] == "Design brief not found: dbf-missing"

    markdown_response = client.get("/api/v1/design-briefs/dbf-missing/one-pager.md")
    assert markdown_response.status_code == 404
    assert markdown_response.json()["detail"] == "Design brief not found: dbf-missing"
