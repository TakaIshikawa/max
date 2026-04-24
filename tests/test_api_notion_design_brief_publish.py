from __future__ import annotations

from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.publisher.notion_pages import NotionPagePublisher
from max.server.app import create_app
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode


def _client(db_path: str) -> TestClient:
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


def _seed_brief(db_path: str) -> str:
    store = Store(db_path=db_path, wal_mode=True)
    try:
        unit = BuildableUnit(
            id="bu-notion-api",
            title="Workspace Review",
            one_liner="Publish design briefs for review",
            category=BuildableCategory.APPLICATION,
            ideation_mode=IdeationMode.DIRECT,
            problem="Design briefs are hard to review outside Max.",
            solution="Create a Notion page with structured sections.",
            value_proposition="Faster design review",
            evidence_rationale="Reviewers requested workspace-native briefs.",
            domain="testing",
        )
        store.insert_buildable_unit(unit)
        return store.insert_design_brief(
            ProjectBrief(
                title="Workspace Review Brief",
                domain="testing",
                theme="notion-publishing",
                lead=Candidate(unit=unit),
                readiness_score=81.0,
                why_this_now="Review needs are increasing.",
                merged_product_concept="A Notion page publisher for briefs.",
                synthesis_rationale="The source idea has clear review demand.",
                mvp_scope=["Create page"],
                first_milestones=["Ship publisher"],
                validation_plan="Publish a brief and review it.",
                risks=["Notion permission errors"],
                source_idea_ids=["bu-notion-api"],
            )
        )
    finally:
        store.close()


def test_publish_design_brief_to_notion_returns_page_result(tmp_path) -> None:
    db_path = str(tmp_path / "api_notion.db")
    brief_id = _seed_brief(db_path)
    seen_payloads: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_payloads.append(request.read())
        return httpx.Response(
            200,
            json={"id": "notion-page-123", "url": "https://notion.so/notion-page-123"},
        )

    publisher = NotionPagePublisher(
        token="secret-token",
        parent_page_id="parent-page",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda _: None,
    )

    with patch("max.server.api.NotionPagePublisher.from_env", return_value=publisher):
        response = _client(db_path).post(
            f"/api/v1/design-briefs/{brief_id}/publish/notion",
            json={
                "token": "secret-token",
                "parent_page_id": "parent-page",
                "dry_run": False,
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["design_brief_id"] == brief_id
    assert data["page_id"] == "notion-page-123"
    assert data["page_url"] == "https://notion.so/notion-page-123"
    assert data["status_code"] == 200
    assert data["dry_run"] is False
    assert "secret-token" not in response.text
    assert seen_payloads
    payload_text = seen_payloads[0].decode()
    assert "Problem" in payload_text
    assert "Solution" in payload_text
    assert "Evidence" in payload_text
    assert "Roadmap" in payload_text
    assert "Notion permission errors" in payload_text


def test_publish_design_brief_to_notion_missing_brief_returns_404(tmp_path) -> None:
    db_path = str(tmp_path / "api_notion_missing.db")
    Store(db_path=db_path, wal_mode=True).close()

    response = _client(db_path).post(
        "/api/v1/design-briefs/dbf-missing/publish/notion",
        json={"token": "secret-token", "parent_page_id": "parent-page"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Design brief not found: dbf-missing"
    assert "secret-token" not in response.text


def test_publish_design_brief_to_notion_validation_failure_returns_4xx(tmp_path) -> None:
    db_path = str(tmp_path / "api_notion_validation.db")
    brief_id = _seed_brief(db_path)

    response = _client(db_path).post(
        f"/api/v1/design-briefs/{brief_id}/publish/notion",
        json={"token": "secret-token"},
    )

    assert response.status_code == 400
    assert "parent_page_id or parent_database_id" in response.json()["detail"]
    assert "secret-token" not in response.text
