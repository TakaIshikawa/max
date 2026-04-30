"""Tests for publishing design briefs to Confluence through the REST API."""

from __future__ import annotations

import base64
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.server.app import create_app
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode


@pytest.fixture
def db_path(tmp_path) -> str:
    path = str(tmp_path / "test_design_brief_confluence_api.db")
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


def _seed_design_brief(db_path: str) -> str:
    store = Store(db_path=db_path, wal_mode=True)
    try:
        unit = BuildableUnit(
            id="bu-confluence-brief",
            title="Confluence Brief Source",
            one_liner="Publish design briefs to Confluence",
            category=BuildableCategory.APPLICATION,
            ideation_mode=IdeationMode.DIRECT,
            problem="Design briefs are hard to review in team rituals.",
            solution="Create a Confluence page from the persisted brief.",
            value_proposition="Product and platform teams can review one durable artifact.",
            buyer="Product lead",
            specific_user="Platform architect",
            workflow_context="Architecture review",
            evidence_rationale="Design leads requested a collaborative documentation target.",
            domain="design-ops",
        )
        store.insert_buildable_unit(unit)
        return store.insert_design_brief(
            ProjectBrief(
                title="Confluence Design Brief",
                domain="design-ops",
                theme="documentation-handoff",
                lead=Candidate(unit=unit),
                readiness_score=88.0,
                why_this_now="Planning artifacts need durable review context.",
                merged_product_concept="A Confluence page publisher for design briefs.",
                synthesis_rationale="The source idea is ready for documentation handoff.",
                mvp_scope=["Render Confluence page payload", "Create Confluence page"],
                first_milestones=["Ship REST endpoint"],
                validation_plan="Dry run, then create a fake transport page.",
                risks=["Incorrect Confluence credentials"],
                source_idea_ids=["bu-confluence-brief", "bu-supporting-confluence"],
            )
        )
    finally:
        store.close()


def test_publish_design_brief_confluence_dry_run_returns_page_payload_without_network(
    client: TestClient,
    db_path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brief_id = _seed_design_brief(db_path)
    monkeypatch.delenv("CONFLUENCE_EMAIL", raising=False)
    monkeypatch.delenv("CONFLUENCE_API_TOKEN", raising=False)
    monkeypatch.delenv("CONFLUENCE_BEARER_TOKEN", raising=False)

    body = {
        "site_url": "https://example.atlassian.net",
        "space_key": "MAX",
        "parent_page_id": "12345",
        "title": "Custom Confluence Brief",
        "dry_run": True,
    }
    first = client.post(f"/api/v1/design-briefs/{brief_id}/publish/confluence", json=body)
    second = client.post(f"/api/v1/design-briefs/{brief_id}/publish/confluence", json=body)

    assert first.status_code == 200
    assert second.status_code == 200
    data = first.json()
    assert data["design_brief_id"] == brief_id
    assert data["space_key"] == "MAX"
    assert data["dry_run"] is True
    assert data["status_code"] is None
    assert data["page_id"] is None
    assert data["page_url"] is None
    assert data["title"] == "Custom Confluence Brief"
    assert data["body_preview"] == second.json()["body_preview"]
    assert data["payload"]["type"] == "page"
    assert data["payload"]["space"] == {"key": "MAX"}
    assert data["payload"]["ancestors"] == [{"id": "12345"}]
    body_html = data["payload"]["body"]["storage"]["value"]
    assert "A Confluence page publisher for design briefs." in body_html
    assert "Buyer: Product lead" in body_html
    assert "Workflow context: Architecture review" in body_html
    assert "Render Confluence page payload" in body_html
    assert "Ship REST endpoint" in body_html
    assert "Dry run, then create a fake transport page." in body_html
    assert "Incorrect Confluence credentials" in body_html
    assert "Source idea: bu-supporting-confluence" in body_html
    assert data["payload"]["metadata"]["design_brief_id"] == brief_id
    assert data["payload"]["metadata"]["source_type"] == "design_brief"
    assert data["provider_metadata"]["page_endpoint"].endswith("/wiki/rest/api/content")
    assert data["request_summary"]["api_token"] is None
    assert data["request_summary"]["bearer_token"] is None
    assert data["publication_attempt"]["target_type"] == "confluence_page"
    assert data["publication_attempt"]["idea_id"] == brief_id
    assert data["publication_attempt"]["status"] == "success"


def test_publish_design_brief_confluence_live_success_with_fake_transport(
    client: TestClient,
    db_path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brief_id = _seed_design_brief(db_path)
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"id": "98765", "_links": {"webui": "/wiki/spaces/MAX/pages/98765/Brief"}},
        )

    def publisher_from_env(**kwargs):
        from max.publisher.confluence_pages import ConfluencePagePublisher

        return ConfluencePagePublisher(
            kwargs["site_url"],
            kwargs["space_key"],
            parent_page_id=kwargs["parent_page_id"],
            email=kwargs["email"],
            api_token=kwargs["api_token"],
            bearer_token=kwargs["bearer_token"],
            timeout=kwargs["timeout"],
            client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )

    monkeypatch.setattr("max.server.api.ConfluencePagePublisher.from_env", publisher_from_env)

    response = client.post(
        f"/api/v1/design-briefs/{brief_id}/publish/confluence",
        json={
            "site_url": "https://example.atlassian.net",
            "space_key": "MAX",
            "parent_page_id": "12345",
            "email": "agent@example.com",
            "api_token": "confluence_api_token",
            "dry_run": False,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["dry_run"] is False
    assert data["status_code"] == 200
    assert data["page_id"] == "98765"
    assert data["page_url"] == "https://example.atlassian.net/wiki/spaces/MAX/pages/98765/Brief"
    assert data["provider_metadata"]["confluence_page_id"] == "98765"
    assert data["request_summary"]["api_token"] == "[redacted]"
    assert "confluence_api_token" not in response.text
    assert data["publication_attempt"]["target_url"] == data["page_url"]
    assert len(requests) == 1

    posted = json.loads(requests[0].content)
    assert posted["title"] == "Confluence Design Brief"
    assert posted["space"] == {"key": "MAX"}
    assert posted["ancestors"] == [{"id": "12345"}]
    assert "A Confluence page publisher for design briefs." in posted["body"]["storage"]["value"]
    expected_auth = base64.b64encode(b"agent@example.com:confluence_api_token").decode("ascii")
    assert requests[0].headers["Authorization"] == f"Basic {expected_auth}"

    store = Store(db_path=db_path, wal_mode=True)
    try:
        attempts = store.list_publication_attempts(brief_id)
        assert len(attempts) == 1
        assert attempts[0]["status"] == "success"
        assert attempts[0]["response_status"] == 200
    finally:
        store.close()


def test_publish_design_brief_confluence_live_requires_credentials_and_records_failure(
    client: TestClient,
    db_path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brief_id = _seed_design_brief(db_path)
    monkeypatch.delenv("CONFLUENCE_EMAIL", raising=False)
    monkeypatch.delenv("CONFLUENCE_API_TOKEN", raising=False)
    monkeypatch.delenv("CONFLUENCE_BEARER_TOKEN", raising=False)

    response = client.post(
        f"/api/v1/design-briefs/{brief_id}/publish/confluence",
        json={"site_url": "https://example.atlassian.net", "space_key": "MAX", "dry_run": False},
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "Confluence email/api_token or bearer_token is required" in detail["message"]
    assert detail["publication_attempt"]["target_type"] == "confluence_page"
    assert detail["publication_attempt"]["status"] == "failure"

    store = Store(db_path=db_path, wal_mode=True)
    try:
        attempts = store.list_publication_attempts(brief_id)
        assert len(attempts) == 1
        assert attempts[0]["status"] == "failure"
    finally:
        store.close()


def test_publish_design_brief_confluence_missing_brief_returns_404(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def publisher_from_env(**kwargs):
        raise AssertionError("missing briefs should not initialize the Confluence publisher")

    monkeypatch.setattr("max.server.api.ConfluencePagePublisher.from_env", publisher_from_env)

    response = client.post(
        "/api/v1/design-briefs/dbf-missing/publish/confluence",
        json={"site_url": "https://example.atlassian.net", "space_key": "MAX"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Design brief not found: dbf-missing"


def test_publish_design_brief_confluence_provider_failure_records_attempt_and_redacts_secret(
    client: TestClient,
    db_path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brief_id = _seed_design_brief(db_path)

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="token=confluence_bearer denied")

    def publisher_from_env(**kwargs):
        from max.publisher.confluence_pages import ConfluencePagePublisher

        return ConfluencePagePublisher(
            kwargs["site_url"],
            kwargs["space_key"],
            bearer_token=kwargs["bearer_token"],
            client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )

    monkeypatch.setattr("max.server.api.ConfluencePagePublisher.from_env", publisher_from_env)

    response = client.post(
        f"/api/v1/design-briefs/{brief_id}/publish/confluence",
        json={
            "site_url": "https://example.atlassian.net",
            "space_key": "MAX",
            "bearer_token": "confluence_bearer",
            "dry_run": False,
        },
    )

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "Confluence page publish failed with HTTP 403" in detail["message"]
    assert "confluence_bearer" not in response.text
    assert detail["publication_attempt"]["target_type"] == "confluence_page"
    assert detail["publication_attempt"]["status"] == "failure"
    assert detail["publication_attempt"]["response_status"] == 403

    store = Store(db_path=db_path, wal_mode=True)
    try:
        attempts = store.list_publication_attempts(brief_id)
        assert len(attempts) == 1
        assert attempts[0]["status"] == "failure"
        assert "confluence_bearer" not in attempts[0]["error"]
    finally:
        store.close()
