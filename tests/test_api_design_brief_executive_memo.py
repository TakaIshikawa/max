"""API tests for design brief executive memo exports."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from max.analysis.design_brief_executive_memo import SCHEMA_VERSION
from max.server.app import create_app
from max.store.db import Store
from tests.test_design_brief_executive_memo import _seed_design_brief


@pytest.fixture
def executive_memo_client(tmp_path) -> tuple[TestClient, str]:
    db_path = str(tmp_path / "executive_memo_api.db")
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


def test_get_design_brief_executive_memo_structured_response(
    executive_memo_client: tuple[TestClient, str],
) -> None:
    client, brief_id = executive_memo_client
    response = client.get(f"/api/v1/design-briefs/{brief_id}/executive-memo")

    assert response.status_code == 200
    data = response.json()
    assert data["schema_version"] == SCHEMA_VERSION
    assert data["design_brief"]["id"] == brief_id
    assert data["decision_summary"]["recommendation"] == "approve-validation"
    assert data["target_segment"]["specific_user"] == "product decision-maker"
    assert data["evidence_highlights"]
    assert data["top_risks"]
    assert data["validation_next_step"]["action"]
    assert data["owner_ask"]


def test_get_design_brief_executive_memo_markdown_export_success(
    executive_memo_client: tuple[TestClient, str],
) -> None:
    client, brief_id = executive_memo_client
    response = client.get(f"/api/v1/design-briefs/{brief_id}/executive-memo.md")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"] == (
        f'attachment; filename="{brief_id}-executive-memo.md"'
    )
    assert response.text.startswith("# Executive Memo: Executive Memo Brief")
    assert "## Decision Summary" in response.text
    assert "## Evidence Highlights" in response.text
    assert "## Risks" in response.text
    assert "## Validation Next Step" in response.text


def test_get_design_brief_executive_memo_missing_brief(
    executive_memo_client: tuple[TestClient, str],
) -> None:
    client, _brief_id = executive_memo_client

    json_response = client.get("/api/v1/design-briefs/dbf-missing/executive-memo")
    assert json_response.status_code == 404
    assert json_response.json()["detail"] == "Design brief not found: dbf-missing"

    markdown_response = client.get("/api/v1/design-briefs/dbf-missing/executive-memo.md")
    assert markdown_response.status_code == 404
    assert markdown_response.json()["detail"] == "Design brief not found: dbf-missing"


def test_existing_design_brief_endpoint_still_returns_404(
    executive_memo_client: tuple[TestClient, str],
) -> None:
    client, _brief_id = executive_memo_client
    response = client.get("/api/v1/design-briefs/dbf-missing")

    assert response.status_code == 404
    assert response.json()["detail"] == "Design brief not found: dbf-missing"
