"""Tests for publishing design briefs to Discord through the REST API."""

from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.publisher.discord_webhook import DiscordWebhookPublisher
from max.server.app import create_app
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode


@pytest.fixture
def db_path(tmp_path) -> str:
    path = str(tmp_path / "test_design_brief_discord_api.db")
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
            id="bu-discord-brief",
            title="Discord Brief Source",
            one_liner="Publish design briefs to Discord",
            category=BuildableCategory.APPLICATION,
            ideation_mode=IdeationMode.DIRECT,
            problem="Design briefs need community review.",
            solution="Post a structured Discord embed.",
            value_proposition="Reviewers see the brief where they collaborate.",
            buyer="Community lead",
            specific_user="Design reviewer",
            workflow_context="Community design review",
            evidence_rationale="Teams requested Discord handoff.",
            domain="devtools",
        )
        store.insert_buildable_unit(unit)
        return store.insert_design_brief(
            ProjectBrief(
                title="Discord Design Brief",
                domain="devtools",
                theme="community-handoff",
                lead=Candidate(unit=unit),
                readiness_score=84.0,
                why_this_now="Creator communities need reviewable design summaries.",
                merged_product_concept="A Discord publisher for persisted design briefs.",
                synthesis_rationale="The source idea is ready for community review.",
                mvp_scope=["Render Discord embed", "Record publication"],
                first_milestones=["Ship Discord endpoint"],
                validation_plan="Dry run, then post with a fake transport.",
                risks=["Discord webhook misconfiguration"],
                source_idea_ids=["bu-discord-brief", "bu-supporting-discord"],
            )
        )
    finally:
        store.close()


def test_publish_design_brief_discord_dry_run_returns_payload_without_network(
    client: TestClient,
    db_path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brief_id = _seed_design_brief(db_path)
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)

    response = client.post(
        f"/api/v1/design-briefs/{brief_id}/publish/discord",
        json={"username": "Max", "dry_run": True},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["design_brief_id"] == brief_id
    assert data["dry_run"] is True
    assert data["response_status"] is None
    assert data["publication_attempt"] is None
    assert data["payload"]["content"] == "[Max] Discord Design Brief"
    assert data["payload"]["username"] == "Max"
    assert data["payload"]["embeds"][0]["footer"]["text"] == "max.discord_webhook | design_brief"
    assert data["provider_metadata"]["provider"] == "discord"
    assert data["provider_metadata"]["source_type"] == "design_brief"
    assert data["request_summary"]["webhook_url"] is None

    store = Store(db_path=db_path, wal_mode=True)
    try:
        assert store.list_publication_attempts(brief_id) == []
    finally:
        store.close()


def test_publish_design_brief_discord_live_success_records_publication_attempt(
    client: TestClient,
    db_path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brief_id = _seed_design_brief(db_path)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(204, text="")

    def publisher_from_env(**kwargs):
        return DiscordWebhookPublisher(
            kwargs["webhook_url"],
            username=kwargs["username"],
            timeout=kwargs["timeout"],
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

    monkeypatch.setattr("max.server.api.DiscordWebhookPublisher.from_env", publisher_from_env)

    response = client.post(
        f"/api/v1/design-briefs/{brief_id}/publish/discord",
        json={
            "webhook_url": "https://discord.com/api/webhooks/123/secret?wait=true",
            "dry_run": False,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["dry_run"] is False
    assert data["response_status"] == 204
    assert data["target_url"] == "https://discord.com/api/webhooks/123/[redacted]?[redacted]"
    assert data["publication_attempt"]["target_type"] == "discord_webhook"
    assert data["publication_attempt"]["status"] == "success"
    assert data["publication_attempt"]["target_url"] == data["target_url"]
    assert data["provider_metadata"]["target_type"] == "discord_webhook"
    assert "secret" not in response.text
    assert len(requests) == 1

    posted = json.loads(requests[0].content)
    assert posted["content"] == "[Max] Discord Design Brief"
    assert posted["embeds"][0]["title"] == "Discord Design Brief"

    store = Store(db_path=db_path, wal_mode=True)
    try:
        attempts = store.list_publication_attempts(brief_id)
        assert len(attempts) == 1
        assert attempts[0]["status"] == "success"
        assert attempts[0]["target_url"].endswith("[redacted]?[redacted]")
    finally:
        store.close()


def test_publish_design_brief_discord_missing_brief_returns_404(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def publisher_from_env(**kwargs):
        raise AssertionError("missing briefs should not initialize the Discord publisher")

    monkeypatch.setattr("max.server.api.DiscordWebhookPublisher.from_env", publisher_from_env)

    response = client.post(
        "/api/v1/design-briefs/dbf-missing/publish/discord",
        json={"webhook_url": "https://discord.com/api/webhooks/123/secret"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Design brief not found: dbf-missing"
    assert "secret" not in response.text


def test_publish_design_brief_discord_live_requires_webhook_and_records_failure(
    client: TestClient,
    db_path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brief_id = _seed_design_brief(db_path)
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)

    response = client.post(
        f"/api/v1/design-briefs/{brief_id}/publish/discord",
        json={"dry_run": False},
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "Discord webhook URL is required" in detail["message"]
    assert detail["publication_attempt"]["target_type"] == "discord_webhook"
    assert detail["publication_attempt"]["status"] == "failure"
    assert detail["request_summary"]["webhook_url"] is None

    store = Store(db_path=db_path, wal_mode=True)
    try:
        attempts = store.list_publication_attempts(brief_id)
        assert len(attempts) == 1
        assert attempts[0]["status"] == "failure"
    finally:
        store.close()


def test_publish_design_brief_discord_provider_4xx_redacts_webhook_secret(
    client: TestClient,
    db_path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brief_id = _seed_design_brief(db_path)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text='{"message":"Invalid Form Body"}')

    def publisher_from_env(**kwargs):
        return DiscordWebhookPublisher(
            kwargs["webhook_url"],
            username=kwargs["username"],
            timeout=kwargs["timeout"],
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

    monkeypatch.setattr("max.server.api.DiscordWebhookPublisher.from_env", publisher_from_env)

    response = client.post(
        f"/api/v1/design-briefs/{brief_id}/publish/discord",
        json={
            "webhook_url": "https://discord.com/api/webhooks/123/secret",
            "dry_run": False,
        },
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["publication_attempt"]["status"] == "failure"
    assert detail["publication_attempt"]["response_status"] == 400
    assert detail["request_summary"]["webhook_url"].endswith("/[redacted]")
    assert "Invalid Form Body" in detail["message"]
    assert "secret" not in response.text
