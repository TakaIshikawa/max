"""Tests for publishing ideas to Monday.com through the REST API."""

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
    path = str(tmp_path / "test_monday_item_api.db")
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
                id="bu-monday001",
                title="Monday Publish Idea",
                one_liner="Publish an idea as a Monday.com item",
                category=BuildableCategory.APPLICATION,
                problem="API clients cannot publish Monday.com items",
                solution="Expose the Monday.com item publisher over REST",
                value_proposition="Agents can publish without shelling out",
                validation_plan="Call the REST endpoint",
                domain="devtools",
                status="approved",
                evidence_rationale="Customer signals mention Monday handoff.",
                evidence_signals=["sig-monday001"],
                inspiring_insights=["ins-monday001"],
            )
        )
        if with_evaluation:
            store.insert_evaluation(_evaluation("bu-monday001"))
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


def test_publish_monday_dry_run_returns_payload_without_token_or_http(client, db_path) -> None:
    _seed_idea(db_path)

    response = client.post(
        "/api/v1/ideas/bu-monday001/publish/monday",
        json={
            "board_id": "board-123",
            "group_id": "topics",
            "item_name": "Launch validation idea",
            "column_values": {"owner": {"personsAndTeams": [{"id": 101, "kind": "person"}]}},
            "dry_run": True,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["board_id"] == "board-123"
    assert data["group_id"] == "topics"
    assert data["dry_run"] is True
    assert data["status_code"] is None
    assert data["item_id"] is None
    assert data["item_url"] is None
    assert data["payload"]["variables"]["item_name"] == "Launch validation idea"
    assert data["payload"]["variables"]["board_id"] == "board-123"
    assert "API clients cannot publish Monday.com items" in (
        data["payload"]["variables"]["column_values"]
    )
    assert data["publication_attempt"]["target_type"] == "monday_item"
    assert data["publication_attempt"]["target_url"] == "https://api.monday.com/v2"
    assert data["publication_attempt"]["status"] == "success"


def test_publish_monday_live_success_records_publication_attempt(
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
                "data": {
                    "create_item": {
                        "id": "item-123",
                        "url": "https://example.monday.com/boards/123/pulses/item-123",
                    }
                }
            },
        )

    def publisher_from_env(**kwargs):
        from max.publisher.monday_items import MondayItemPublisher

        return MondayItemPublisher(
            kwargs["board_id"],
            api_token=kwargs["api_token"],
            group_id=kwargs["group_id"],
            item_name=kwargs["item_name"],
            column_values=kwargs["column_values"],
            api_url=kwargs["api_url"] or "https://api.monday.com/v2",
            timeout=kwargs["timeout"],
            max_retries=kwargs["max_retries"],
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

    monkeypatch.setattr("max.server.api.MondayItemPublisher.from_env", publisher_from_env)

    response = client.post(
        "/api/v1/ideas/bu-monday001/publish/monday",
        json={
            "board_id": "board-123",
            "group_id": "topics",
            "api_token": "monday_pat",
            "dry_run": False,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["dry_run"] is False
    assert data["status_code"] == 200
    assert data["item_id"] == "item-123"
    assert data["item_url"] == "https://example.monday.com/boards/123/pulses/item-123"
    assert data["publication_attempt"]["target_type"] == "monday_item"
    assert data["publication_attempt"]["target_url"] == data["item_url"]
    assert data["publication_attempt"]["status"] == "success"
    assert data["publication_attempt"]["response_status"] == 200
    assert len(requests) == 1
    assert requests[0].headers["Authorization"] == "monday_pat"

    store = Store(db_path=db_path, wal_mode=True)
    try:
        attempts = store.list_publication_attempts("bu-monday001")
        assert len(attempts) == 1
        assert attempts[0]["target_type"] == "monday_item"
        assert attempts[0]["target_url"] == data["item_url"]
        assert attempts[0]["status"] == "success"
    finally:
        store.close()


def test_publish_monday_http_failure_records_failed_attempt_and_redacts_token(
    client,
    db_path,
    monkeypatch,
) -> None:
    _seed_idea(db_path)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="invalid token=monday_secret")

    def publisher_from_env(**kwargs):
        from max.publisher.monday_items import MondayItemPublisher

        return MondayItemPublisher(
            kwargs["board_id"],
            api_token=kwargs["api_token"],
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

    monkeypatch.setattr("max.server.api.MondayItemPublisher.from_env", publisher_from_env)

    response = client.post(
        "/api/v1/ideas/bu-monday001/publish/monday",
        json={
            "board_id": "board-123",
            "api_token": "monday_secret",
            "dry_run": False,
        },
    )

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "Monday.com item publish failed with HTTP 401" in detail["message"]
    assert "monday_secret" not in detail["message"]
    assert detail["publication_attempt"]["target_type"] == "monday_item"
    assert detail["publication_attempt"]["status"] == "failure"
    assert detail["publication_attempt"]["response_status"] == 401

    store = Store(db_path=db_path, wal_mode=True)
    try:
        attempts = store.list_publication_attempts("bu-monday001")
        assert len(attempts) == 1
        assert attempts[0]["status"] == "failure"
        assert "monday_secret" not in attempts[0]["error"]
    finally:
        store.close()


def test_publish_monday_live_requires_token_and_records_failed_attempt(
    client,
    db_path,
    monkeypatch,
) -> None:
    _seed_idea(db_path)
    monkeypatch.delenv("MONDAY_API_TOKEN", raising=False)

    response = client.post(
        "/api/v1/ideas/bu-monday001/publish/monday",
        json={
            "board_id": "board-123",
            "dry_run": False,
        },
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "MONDAY_API_TOKEN is required" in detail["message"]
    assert detail["publication_attempt"]["target_type"] == "monday_item"
    assert detail["publication_attempt"]["status"] == "failure"


def test_publish_monday_missing_board_fails_before_network(client, db_path, monkeypatch) -> None:
    _seed_idea(db_path)
    monkeypatch.delenv("MONDAY_BOARD_ID", raising=False)

    response = client.post(
        "/api/v1/ideas/bu-monday001/publish/monday",
        json={"api_token": "monday_pat", "dry_run": False},
    )

    assert response.status_code == 400
    assert "Monday board_id is required" in response.json()["detail"]


def test_publish_monday_missing_idea(client, monkeypatch) -> None:
    def publisher_from_env(**kwargs):
        raise AssertionError("missing ideas should not initialize the Monday publisher")

    monkeypatch.setattr("max.server.api.MondayItemPublisher.from_env", publisher_from_env)

    response = client.post(
        "/api/v1/ideas/missing/publish/monday",
        json={"board_id": "board-123"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Idea not found: missing"


def test_publish_monday_missing_evaluation(client, db_path) -> None:
    _seed_idea(db_path, with_evaluation=False)

    response = client.post(
        "/api/v1/ideas/bu-monday001/publish/monday",
        json={"board_id": "board-123"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Evaluation not found: bu-monday001"


def test_publish_monday_schema_validation(client, db_path) -> None:
    _seed_idea(db_path)

    response = client.post(
        "/api/v1/ideas/bu-monday001/publish/monday",
        json={
            "board_id": "board-123",
            "dry_run": True,
            "max_retries": 6,
        },
    )

    assert response.status_code == 422
