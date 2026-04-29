"""Tests for publishing design briefs to Teams through the REST API."""

from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.publisher.teams_webhook import TeamsWebhookPublisher
from max.server.app import create_app
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode


@pytest.fixture
def db_path(tmp_path) -> str:
    path = str(tmp_path / "test_design_brief_teams_api.db")
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
            id="bu-teams-brief",
            title="Teams Brief Source",
            one_liner="Publish design briefs to Teams",
            category=BuildableCategory.APPLICATION,
            ideation_mode=IdeationMode.DIRECT,
            problem="Design briefs need team review.",
            solution="Post a structured Teams summary.",
            value_proposition="Reviewers see the brief where they work.",
            buyer="Product lead",
            specific_user="Design reviewer",
            workflow_context="Design synthesis review",
            evidence_rationale="Teams requested Teams handoff.",
            domain="devtools",
        )
        store.insert_buildable_unit(unit)
        return store.insert_design_brief(
            ProjectBrief(
                title="Teams Design Brief",
                domain="devtools",
                theme="review-handoff",
                lead=Candidate(unit=unit),
                readiness_score=86.0,
                why_this_now="Review teams need faster handoff.",
                merged_product_concept="A Teams publisher for persisted design briefs.",
                synthesis_rationale="The source idea is ready for design review.",
                mvp_scope=["Render Teams payload", "Record publication"],
                first_milestones=["Ship Teams endpoint"],
                validation_plan="Dry run, then post with a fake transport.",
                risks=["Teams webhook misconfiguration"],
                source_idea_ids=["bu-teams-brief", "bu-supporting-teams"],
            )
        )
    finally:
        store.close()


def test_publish_design_brief_teams_dry_run_returns_payload_without_network(
    client: TestClient,
    db_path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brief_id = _seed_design_brief(db_path)

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry-run publishing should not call Teams")

    def publisher_from_env(**kwargs):
        return TeamsWebhookPublisher(
            kwargs["webhook_url"],
            timeout=kwargs["timeout"],
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

    monkeypatch.setattr("max.server.api.TeamsWebhookPublisher.from_env", publisher_from_env)

    response = client.post(
        f"/api/v1/design-briefs/{brief_id}/publish/teams",
        json={
            "webhook_url": "https://example.webhook.office.com/webhookb2/token?sig=secret",
            "title": "Teams Override",
            "dry_run": True,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["design_brief_id"] == brief_id
    assert data["dry_run"] is True
    assert data["response_status"] is None
    assert data["publication_attempt"] is None
    assert data["payload"]["@type"] == "MessageCard"
    assert data["payload"]["title"] == "[Max] Teams Override"
    assert data["payload"]["metadata"]["source_type"] == "design_brief"
    assert data["payload"]["metadata"]["design_brief_id"] == brief_id
    assert data["request_summary"]["webhook_url"].endswith("/[redacted]?[redacted]")
    assert "secret" not in response.text

    store = Store(db_path=db_path, wal_mode=True)
    try:
        assert store.list_publication_attempts(brief_id) == []
    finally:
        store.close()


def test_publish_design_brief_teams_live_success_records_publication_attempt(
    client: TestClient,
    db_path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brief_id = _seed_design_brief(db_path)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, text="1")

    def publisher_from_env(**kwargs):
        return TeamsWebhookPublisher(
            kwargs["webhook_url"],
            timeout=kwargs["timeout"],
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

    monkeypatch.setattr("max.server.api.TeamsWebhookPublisher.from_env", publisher_from_env)

    response = client.post(
        f"/api/v1/design-briefs/{brief_id}/publish/teams",
        json={
            "webhook_url": "https://example.webhook.office.com/webhookb2/token",
            "dry_run": False,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["dry_run"] is False
    assert data["response_status"] == 200
    assert data["target_url"] == "https://example.webhook.office.com/webhookb2/[redacted]"
    assert data["publication_attempt"]["target_type"] == "teams_webhook"
    assert data["publication_attempt"]["status"] == "success"
    assert data["publication_attempt"]["target_url"] == data["target_url"]
    assert "token" not in response.text
    assert len(requests) == 1

    posted = json.loads(requests[0].content)
    assert posted["@type"] == "MessageCard"
    assert posted["metadata"]["source_type"] == "design_brief"
    assert posted["metadata"]["design_brief_id"] == brief_id

    store = Store(db_path=db_path, wal_mode=True)
    try:
        attempts = store.list_publication_attempts(brief_id)
        assert len(attempts) == 1
        assert attempts[0]["status"] == "success"
        assert attempts[0]["target_type"] == "teams_webhook"
        assert attempts[0]["target_url"].endswith("/[redacted]")
    finally:
        store.close()


def test_publish_design_brief_teams_missing_brief_returns_404(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def publisher_from_env(**kwargs):
        raise AssertionError("missing briefs should not initialize the Teams publisher")

    monkeypatch.setattr("max.server.api.TeamsWebhookPublisher.from_env", publisher_from_env)

    response = client.post(
        "/api/v1/design-briefs/dbf-missing/publish/teams",
        json={"webhook_url": "https://example.webhook.office.com/webhookb2/token"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Design brief not found: dbf-missing"
    assert "token" not in response.text


def test_publish_design_brief_teams_live_requires_webhook_and_records_failure(
    client: TestClient,
    db_path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brief_id = _seed_design_brief(db_path)
    monkeypatch.delenv("TEAMS_WEBHOOK_URL", raising=False)

    response = client.post(
        f"/api/v1/design-briefs/{brief_id}/publish/teams",
        json={"dry_run": False},
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "Teams webhook URL is required" in detail["message"]
    assert detail["publication_attempt"]["target_type"] == "teams_webhook"
    assert detail["publication_attempt"]["status"] == "failure"
    assert detail["request_summary"]["webhook_url"] is None

    store = Store(db_path=db_path, wal_mode=True)
    try:
        attempts = store.list_publication_attempts(brief_id)
        assert len(attempts) == 1
        assert attempts[0]["status"] == "failure"
    finally:
        store.close()


def test_publish_design_brief_teams_provider_error_redacts_webhook_secret(
    client: TestClient,
    db_path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brief_id = _seed_design_brief(db_path)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="workflow failed")

    def publisher_from_env(**kwargs):
        return TeamsWebhookPublisher(
            kwargs["webhook_url"],
            timeout=kwargs["timeout"],
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

    monkeypatch.setattr("max.server.api.TeamsWebhookPublisher.from_env", publisher_from_env)

    response = client.post(
        f"/api/v1/design-briefs/{brief_id}/publish/teams",
        json={
            "webhook_url": "https://example.webhook.office.com/webhookb2/token",
            "dry_run": False,
        },
    )

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert detail["publication_attempt"]["status"] == "failure"
    assert detail["publication_attempt"]["response_status"] == 500
    assert detail["request_summary"]["webhook_url"].endswith("/[redacted]")
    assert "workflow failed" in detail["message"]
    assert "token" not in response.text
