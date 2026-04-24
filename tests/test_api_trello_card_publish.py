"""Tests for publishing ideas to Trello through the REST API."""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from max.server.app import create_app
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit
from max.types.evaluation import DimensionScore, UtilityEvaluation


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "test_trello_card_api.db")
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


def _seed_idea(db_path: str, *, with_evaluation: bool = True) -> None:
    store = Store(db_path=db_path, wal_mode=True)
    try:
        store.insert_buildable_unit(
            BuildableUnit(
                id="bu-trello001",
                title="Trello Publish Idea",
                one_liner="Publish an idea as a Trello card",
                category=BuildableCategory.APPLICATION,
                problem="API clients cannot publish Trello cards",
                solution="Expose the Trello card publisher over REST",
                value_proposition="Agents can publish without shelling out",
                validation_plan="Call the REST endpoint",
                domain="devtools",
                status="approved",
                evidence_rationale="Customer signals mention Trello handoff.",
                evidence_signals=["sig-trello001"],
                inspiring_insights=["ins-trello001"],
            )
        )
        if with_evaluation:
            store.insert_evaluation(_evaluation("bu-trello001"))
    finally:
        store.close()


def _evaluation(unit_id: str) -> UtilityEvaluation:
    score = DimensionScore(value=8.0, confidence=0.7, reasoning="test")
    return UtilityEvaluation(
        buildable_unit_id=unit_id,
        pain_severity=score,
        addressable_scale=score,
        build_effort=score,
        composability=score,
        competitive_density=score,
        timing_fit=score,
        compounding_value=score,
        overall_score=80.0,
        recommendation="yes",
    )


def test_publish_trello_dry_run_returns_payload_without_key_token_or_http(client, db_path) -> None:
    _seed_idea(db_path)

    response = client.post(
        "/api/v1/ideas/bu-trello001/publish/trello",
        json={
            "list_id": "list-123",
            "labels": ["label-1", "label-2"],
            "due": "2026-05-01",
            "dry_run": True,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["list_id"] == "list-123"
    assert data["dry_run"] is True
    assert data["status_code"] is None
    assert data["card_id"] is None
    assert data["card_url"] is None
    assert data["payload"]["name"] == "[Max] Trello Publish Idea"
    assert data["payload"]["idList"] == "list-123"
    assert "label-1" in data["payload"]["labels"]
    assert "label-2" in data["payload"]["labels"]
    assert data["payload"]["due"] == "2026-05-01"
    assert "Call the REST endpoint" in data["payload"]["desc"]
    assert data["publication_attempt"]["target_type"] == "trello_card"
    assert data["publication_attempt"]["target_url"] == "https://api.trello.com/1/cards"
    assert data["publication_attempt"]["status"] == "success"


def test_publish_trello_live_success_records_publication_attempt(
    client,
    db_path,
    monkeypatch,
) -> None:
    _seed_idea(db_path)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "id": "card-123",
                "url": "https://trello.com/c/card123/1-trello-publish-idea",
            },
        )

    def publisher_from_env(**kwargs):
        from max.publisher.trello_cards import TrelloCardPublisher

        return TrelloCardPublisher(
            kwargs["list_id"],
            key=kwargs["key"],
            token=kwargs["token"],
            api_url=kwargs["api_url"] or "https://api.trello.com/1",
            labels=kwargs["labels"],
            due=kwargs["due"],
            timeout=kwargs["timeout"],
            max_retries=kwargs["max_retries"],
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

    monkeypatch.setattr("max.server.api.TrelloCardPublisher.from_env", publisher_from_env)

    response = client.post(
        "/api/v1/ideas/bu-trello001/publish/trello",
        json={
            "list_id": "list-123",
            "key": "trello_key",
            "token": "trello_token",
            "labels": ["label-1"],
            "dry_run": False,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["dry_run"] is False
    assert data["status_code"] == 200
    assert data["card_id"] == "card-123"
    assert data["card_url"] == "https://trello.com/c/card123/1-trello-publish-idea"
    assert data["publication_attempt"]["target_type"] == "trello_card"
    assert data["publication_attempt"]["target_url"] == data["card_url"]
    assert data["publication_attempt"]["status"] == "success"
    assert data["publication_attempt"]["response_status"] == 200
    assert len(requests) == 1

    store = Store(db_path=db_path, wal_mode=True)
    try:
        attempts = store.list_publication_attempts("bu-trello001")
        assert len(attempts) == 1
        assert attempts[0]["target_type"] == "trello_card"
        assert attempts[0]["target_url"] == data["card_url"]
        assert attempts[0]["status"] == "success"
    finally:
        store.close()


def test_publish_trello_http_failure_records_failed_attempt(
    client,
    db_path,
    monkeypatch,
) -> None:
    _seed_idea(db_path)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="invalid token=trello_secret key=trello_key")

    def publisher_from_env(**kwargs):
        from max.publisher.trello_cards import TrelloCardPublisher

        return TrelloCardPublisher(
            kwargs["list_id"],
            key=kwargs["key"],
            token=kwargs["token"],
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

    monkeypatch.setattr("max.server.api.TrelloCardPublisher.from_env", publisher_from_env)

    response = client.post(
        "/api/v1/ideas/bu-trello001/publish/trello",
        json={
            "list_id": "list-123",
            "key": "trello_key",
            "token": "trello_token",
            "dry_run": False,
        },
    )

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "Trello card publish failed with HTTP 401" in detail["message"]
    assert "trello_secret" not in detail["message"]
    assert "trello_key" not in detail["message"]
    assert detail["publication_attempt"]["target_type"] == "trello_card"
    assert detail["publication_attempt"]["status"] == "failure"
    assert detail["publication_attempt"]["response_status"] == 401

    store = Store(db_path=db_path, wal_mode=True)
    try:
        attempts = store.list_publication_attempts("bu-trello001")
        assert len(attempts) == 1
        assert attempts[0]["status"] == "failure"
        assert "trello_secret" not in attempts[0]["error"]
        assert "trello_key" not in attempts[0]["error"]
    finally:
        store.close()


def test_publish_trello_missing_idea(client, monkeypatch) -> None:
    def publisher_from_env(**kwargs):
        raise AssertionError("missing ideas should not initialize the Trello publisher")

    monkeypatch.setattr("max.server.api.TrelloCardPublisher.from_env", publisher_from_env)

    response = client.post(
        "/api/v1/ideas/missing/publish/trello",
        json={"list_id": "list-123"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Idea not found: missing"


def test_publish_trello_missing_evaluation(client, db_path) -> None:
    _seed_idea(db_path, with_evaluation=False)

    response = client.post(
        "/api/v1/ideas/bu-trello001/publish/trello",
        json={"list_id": "list-123"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Evaluation not found: bu-trello001"


def test_publish_trello_live_requires_auth_and_records_failed_attempt(
    client,
    db_path,
    monkeypatch,
) -> None:
    _seed_idea(db_path)
    monkeypatch.delenv("TRELLO_KEY", raising=False)
    monkeypatch.delenv("TRELLO_TOKEN", raising=False)

    response = client.post(
        "/api/v1/ideas/bu-trello001/publish/trello",
        json={"list_id": "list-123", "dry_run": False},
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "TRELLO_KEY and TRELLO_TOKEN are required" in detail["message"]
    assert detail["publication_attempt"]["target_type"] == "trello_card"
    assert detail["publication_attempt"]["status"] == "failure"

    store = Store(db_path=db_path, wal_mode=True)
    try:
        attempts = store.list_publication_attempts("bu-trello001")
        assert len(attempts) == 1
        assert attempts[0]["status"] == "failure"
        assert "TRELLO_KEY and TRELLO_TOKEN" in attempts[0]["error"]
    finally:
        store.close()


def test_publish_trello_missing_list_id_returns_actionable_error(client, db_path) -> None:
    _seed_idea(db_path)

    response = client.post(
        "/api/v1/ideas/bu-trello001/publish/trello",
        json={"dry_run": True},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "Trello list_id is required; pass list_id or set TRELLO_LIST_ID"
    )
