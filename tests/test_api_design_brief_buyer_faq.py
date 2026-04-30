"""API tests for design brief buyer FAQ exports."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from max.analysis.design_brief_buyer_faq import SCHEMA_VERSION
from max.server.app import create_app
from max.server.dependencies import get_store
from max.store.db import Store
from tests.test_design_brief_buyer_faq import _seed_supported_brief


@pytest.fixture
def db_path(tmp_path) -> str:
    path = str(tmp_path / "test_design_brief_buyer_faq_api.db")
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
        return _seed_supported_brief(store)
    finally:
        store.close()


def test_get_design_brief_buyer_faq_json(
    client: TestClient,
    db_path: str,
) -> None:
    brief_id = _seed_design_brief(db_path)

    response = client.get(f"/api/v1/design-briefs/{brief_id}/buyer-faq")

    assert response.status_code == 200
    data = response.json()
    assert data["schema_version"] == SCHEMA_VERSION
    assert data["kind"] == "max.design_brief.buyer_faq"
    assert data["design_brief"]["id"] == brief_id
    assert data["design_brief"]["title"] == "Buyer FAQ Brief"
    assert data["summary"]["buyer"] == "VP of Sales"
    assert data["summary"]["question_count"] == 7
    assert data["questions"][0]["id"] == "FAQ1"
    assert data["concern_areas"][0]["title"] == "Problem Fit"


def test_get_design_brief_buyer_faq_markdown_download(
    client: TestClient,
    db_path: str,
) -> None:
    brief_id = _seed_design_brief(db_path)

    response = client.get(f"/api/v1/design-briefs/{brief_id}/buyer-faq.md")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"] == (
        f'attachment; filename="{brief_id}-buyer-faq.md"'
    )
    assert response.text.startswith("# Buyer FAQ: Buyer FAQ Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in response.text
    assert f"Design brief: `{brief_id}`" in response.text
    assert "## Problem Fit" in response.text
    assert "## Security Or Compliance" in response.text
    assert "## Proof Points" in response.text


def test_get_design_brief_buyer_faq_missing_brief_returns_404(
    client: TestClient,
) -> None:
    json_response = client.get("/api/v1/design-briefs/dbf-missing/buyer-faq")
    markdown_response = client.get("/api/v1/design-briefs/dbf-missing/buyer-faq.md")

    assert json_response.status_code == 404
    assert json_response.json()["detail"] == "Design brief not found: dbf-missing"
    assert markdown_response.status_code == 404
    assert markdown_response.json()["detail"] == "Design brief not found: dbf-missing"
