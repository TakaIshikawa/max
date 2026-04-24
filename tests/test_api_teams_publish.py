"""Tests for the Teams publish API."""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from max.server.app import create_app
from max.store.db import Store


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "test_api_teams.db")
    store = Store(db_path=path, wal_mode=True)
    store.close()
    return path


@pytest.fixture
def client(db_path):
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


@pytest.fixture
def seeded_db(db_path, sample_signal, sample_insight, sample_unit, sample_evaluation):
    store = Store(db_path=db_path, wal_mode=True)
    store.insert_signal(sample_signal)
    store.insert_insight(sample_insight)
    store.insert_buildable_unit(sample_unit)
    store.insert_evaluation(sample_evaluation)
    store.close()
    return db_path


@pytest.fixture
def seeded_client(seeded_db):
    from max.server.dependencies import get_store

    app = create_app()

    def override_get_store():
        store = Store(db_path=seeded_db, wal_mode=True)
        try:
            yield store
        finally:
            store.close()

    app.dependency_overrides[get_store] = override_get_store
    return TestClient(app)


def test_publish_idea_to_teams_dry_run_returns_payload_without_attempt(
    seeded_client,
    seeded_db,
) -> None:
    resp = seeded_client.post(
        "/api/v1/ideas/bu-test001/publish/teams",
        json={
            "webhook_url": "https://example.webhook.office.com/webhookb2/token?sig=secret",
            "title": "Teams Override",
            "dry_run": True,
            "include_evidence": False,
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["dry_run"] is True
    assert data["response_status"] is None
    assert data["publication_attempt"] is None
    assert data["target_url"] == "https://example.webhook.office.com/webhookb2/[redacted]?[redacted]"
    assert "secret" not in data["target_url"]
    assert data["payload"]["@type"] == "MessageCard"
    assert data["payload"]["title"] == "[Max] Teams Override"
    assert data["payload"]["metadata"]["provider"] == "teams"
    assert [section.get("title") for section in data["payload"]["sections"]] == [None, "Metadata"]

    store = Store(db_path=seeded_db, wal_mode=True)
    try:
        assert store.list_publication_attempts("bu-test001") == []
    finally:
        store.close()


def test_publish_idea_to_teams_success_records_publication_attempt(
    seeded_client,
    seeded_db,
    monkeypatch,
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, text="1")

    def publisher_from_env(**kwargs):
        from max.publisher.teams_webhook import TeamsWebhookPublisher

        return TeamsWebhookPublisher(
            kwargs["webhook_url"],
            timeout=kwargs["timeout"],
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

    monkeypatch.setattr("max.server.api.TeamsWebhookPublisher.from_env", publisher_from_env)

    resp = seeded_client.post(
        "/api/v1/ideas/bu-test001/publish/teams",
        json={"webhook_url": "https://example.webhook.office.com/webhookb2/token"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["dry_run"] is False
    assert data["response_status"] == 200
    assert data["publication_attempt"]["target_type"] == "teams_webhook"
    assert data["publication_attempt"]["status"] == "success"
    assert data["publication_attempt"]["target_url"] == (
        "https://example.webhook.office.com/webhookb2/[redacted]"
    )
    assert len(requests) == 1

    store = Store(db_path=seeded_db, wal_mode=True)
    try:
        attempts = store.list_publication_attempts("bu-test001")
        assert len(attempts) == 1
        assert attempts[0]["status"] == "success"
        assert attempts[0]["target_type"] == "teams_webhook"
        assert attempts[0]["response_status"] == 200
        assert "token" not in attempts[0]["target_url"]
    finally:
        store.close()


def test_publish_idea_to_teams_error_records_failed_attempt(
    seeded_client,
    seeded_db,
    monkeypatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="workflow failed")

    def publisher_from_env(**kwargs):
        from max.publisher.teams_webhook import TeamsWebhookPublisher

        return TeamsWebhookPublisher(
            kwargs["webhook_url"],
            timeout=kwargs["timeout"],
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

    monkeypatch.setattr("max.server.api.TeamsWebhookPublisher.from_env", publisher_from_env)

    resp = seeded_client.post(
        "/api/v1/ideas/bu-test001/publish/teams",
        json={"webhook_url": "https://example.webhook.office.com/webhookb2/token"},
    )

    assert resp.status_code == 502
    detail = resp.json()["detail"]
    assert detail["publication_attempt"]["status"] == "failure"
    assert detail["publication_attempt"]["target_type"] == "teams_webhook"
    assert detail["publication_attempt"]["target_url"] == (
        "https://example.webhook.office.com/webhookb2/[redacted]"
    )
    assert "workflow failed" in detail["message"]

    store = Store(db_path=seeded_db, wal_mode=True)
    try:
        attempts = store.list_publication_attempts("bu-test001")
        assert len(attempts) == 1
        assert attempts[0]["status"] == "failure"
        assert attempts[0]["response_status"] == 500
        assert "workflow failed" in attempts[0]["error"]
        assert "token" not in attempts[0]["target_url"]
    finally:
        store.close()


def test_publish_idea_to_teams_missing_idea_does_not_call_webhook(
    client,
    monkeypatch,
) -> None:
    def publisher_from_env(**kwargs):
        raise AssertionError("missing ideas should not initialize or call the webhook")

    monkeypatch.setattr("max.server.api.TeamsWebhookPublisher.from_env", publisher_from_env)

    resp = client.post(
        "/api/v1/ideas/nonexistent/publish/teams",
        json={"webhook_url": "https://example.webhook.office.com/webhookb2/token"},
    )

    assert resp.status_code == 404


def test_publish_idea_to_teams_rejects_invalid_schema(seeded_client) -> None:
    resp = seeded_client.post(
        "/api/v1/ideas/bu-test001/publish/teams",
        json={
            "webhook_url": "https://example.webhook.office.com/webhookb2/token",
            "title": "",
            "timeout": 0,
        },
    )

    assert resp.status_code == 422
