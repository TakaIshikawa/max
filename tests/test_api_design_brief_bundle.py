"""API tests for design brief bundle exports."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from max.analysis.design_brief_bundle import SCHEMA_VERSION
from max.server.app import create_app
from max.store.db import Store
from tests.test_design_brief_bundle import _seed_design_brief


@pytest.fixture
def bundle_client(tmp_path) -> tuple[TestClient, str]:
    db_path = str(tmp_path / "api_design_brief_bundle.db")
    store = Store(db_path=db_path, wal_mode=True)
    try:
        brief_id = _seed_design_brief(store)
    finally:
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


def test_get_design_brief_bundle_structured_response(bundle_client: tuple[TestClient, str]) -> None:
    client, brief_id = bundle_client
    response = client.get(f"/api/v1/design-briefs/{brief_id}/bundle")

    assert response.status_code == 200
    data = response.json()
    assert data["schema_version"] == SCHEMA_VERSION
    assert data["design_brief"]["id"] == brief_id
    assert data["blueprint_source_brief"]["design_brief"]["id"] == brief_id
    assert data["validation_plan"]["design_brief"]["id"] == brief_id
    assert data["evidence_matrix"]["design_brief"]["id"] == brief_id
    assert data["risk_register"]["design_brief"]["id"] == brief_id
    assert data["roadmap"]["design_brief"]["id"] == brief_id
    assert data["prd"]["design_brief"]["id"] == brief_id
    assert data["market_sizing"]["design_brief"]["id"] == brief_id
    assert data["competitive_landscape"]["design_brief"]["id"] == brief_id
    assert data["artifact_status"]["prd"]["status"] == "generated"


def test_get_design_brief_bundle_markdown_response(bundle_client: tuple[TestClient, str]) -> None:
    client, brief_id = bundle_client
    response = client.get(f"/api/v1/design-briefs/{brief_id}/bundle.md")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"] == (
        f'attachment; filename="{brief_id}-bundle.md"'
    )
    assert response.text.startswith("# Design Brief Bundle: Bundle Export Brief")
    assert "## Artifact Status" in response.text
    assert "## Validation Plan" in response.text
    assert "## PRD" in response.text
    assert "## Competitive Landscape" in response.text


def test_get_design_brief_bundle_missing_brief(bundle_client: tuple[TestClient, str]) -> None:
    client, _brief_id = bundle_client

    json_response = client.get("/api/v1/design-briefs/dbf-missing/bundle")
    assert json_response.status_code == 404
    assert json_response.json()["detail"] == "Design brief not found: dbf-missing"

    markdown_response = client.get("/api/v1/design-briefs/dbf-missing/bundle.md")
    assert markdown_response.status_code == 404
    assert markdown_response.json()["detail"] == "Design brief not found: dbf-missing"
