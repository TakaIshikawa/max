"""Tests for publishing ideas to ClickUp through the REST API."""

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
    path = str(tmp_path / "test_clickup_task_api.db")
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
                id="bu-clickup001",
                title="ClickUp Publish Idea",
                one_liner="Publish an idea as a ClickUp task",
                category=BuildableCategory.APPLICATION,
                problem="API clients cannot publish ClickUp tasks",
                solution="Expose the ClickUp task publisher over REST",
                value_proposition="Agents can publish without shelling out",
                validation_plan="Call the REST endpoint",
                domain="devtools",
                status="approved",
                evidence_rationale="Customer signals mention ClickUp handoff.",
                evidence_signals=["sig-clickup001"],
                inspiring_insights=["ins-clickup001"],
            )
        )
        if with_evaluation:
            store.insert_evaluation(_evaluation("bu-clickup001"))
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


def test_publish_clickup_dry_run_returns_payload_without_token_or_http(client, db_path) -> None:
    _seed_idea(db_path)

    response = client.post(
        "/api/v1/ideas/bu-clickup001/publish/clickup",
        json={
            "list_id": "list-123",
            "assignees": [101, 202],
            "tags": ["handoff"],
            "priority": 2,
            "due_date": 1777593600000,
            "custom_fields": [{"id": "field-1", "value": "max"}],
            "dry_run": True,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["list_id"] == "list-123"
    assert data["dry_run"] is True
    assert data["status_code"] is None
    assert data["task_id"] is None
    assert data["task_url"] is None
    assert data["payload"]["name"] == "[Max] ClickUp Publish Idea"
    assert data["payload"]["list_id"] == "list-123"
    assert data["payload"]["assignees"] == [101, 202]
    assert data["payload"]["priority"] == 2
    assert data["payload"]["due_date"] == 1777593600000
    assert data["payload"]["custom_fields"] == [{"id": "field-1", "value": "max"}]
    assert "Call the REST endpoint" in data["payload"]["description"]
    assert data["publication_attempt"]["target_type"] == "clickup_task"
    assert data["publication_attempt"]["target_url"] == (
        "https://api.clickup.com/api/v2/list/list-123/task"
    )
    assert data["publication_attempt"]["status"] == "success"


def test_publish_clickup_live_success_records_publication_attempt(
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
            json={"id": "task-123", "url": "https://app.clickup.com/t/task-123"},
        )

    def publisher_from_env(**kwargs):
        from max.publisher.clickup_tasks import ClickUpTaskPublisher

        return ClickUpTaskPublisher(
            kwargs["list_id"],
            api_token=kwargs["api_token"],
            api_url=kwargs["api_url"] or "https://api.clickup.com/api/v2",
            assignees=kwargs["assignees"],
            tags=kwargs["tags"],
            priority=kwargs["priority"],
            due_date=kwargs["due_date"],
            custom_fields=kwargs["custom_fields"],
            timeout=kwargs["timeout"],
            max_retries=kwargs["max_retries"],
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

    monkeypatch.setattr("max.server.api.ClickUpTaskPublisher.from_env", publisher_from_env)

    response = client.post(
        "/api/v1/ideas/bu-clickup001/publish/clickup",
        json={
            "list_id": "list-123",
            "api_token": "clickup_pat",
            "tags": ["handoff"],
            "dry_run": False,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["dry_run"] is False
    assert data["status_code"] == 200
    assert data["task_id"] == "task-123"
    assert data["task_url"] == "https://app.clickup.com/t/task-123"
    assert data["publication_attempt"]["target_type"] == "clickup_task"
    assert data["publication_attempt"]["target_url"] == data["task_url"]
    assert data["publication_attempt"]["status"] == "success"
    assert data["publication_attempt"]["response_status"] == 200
    assert len(requests) == 1

    store = Store(db_path=db_path, wal_mode=True)
    try:
        attempts = store.list_publication_attempts("bu-clickup001")
        assert len(attempts) == 1
        assert attempts[0]["target_type"] == "clickup_task"
        assert attempts[0]["target_url"] == data["task_url"]
        assert attempts[0]["status"] == "success"
    finally:
        store.close()


def test_publish_clickup_http_failure_records_failed_attempt(
    client,
    db_path,
    monkeypatch,
) -> None:
    _seed_idea(db_path)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"err": "Forbidden"})

    def publisher_from_env(**kwargs):
        from max.publisher.clickup_tasks import ClickUpTaskPublisher

        return ClickUpTaskPublisher(
            kwargs["list_id"],
            api_token=kwargs["api_token"],
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

    monkeypatch.setattr("max.server.api.ClickUpTaskPublisher.from_env", publisher_from_env)

    response = client.post(
        "/api/v1/ideas/bu-clickup001/publish/clickup",
        json={
            "list_id": "list-123",
            "api_token": "clickup_pat",
            "dry_run": False,
        },
    )

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "ClickUp task publish failed with HTTP 403" in detail["message"]
    assert detail["publication_attempt"]["target_type"] == "clickup_task"
    assert detail["publication_attempt"]["status"] == "failure"
    assert detail["publication_attempt"]["response_status"] == 403

    store = Store(db_path=db_path, wal_mode=True)
    try:
        attempts = store.list_publication_attempts("bu-clickup001")
        assert len(attempts) == 1
        assert attempts[0]["status"] == "failure"
        assert "HTTP 403" in attempts[0]["error"]
    finally:
        store.close()


def test_publish_clickup_live_requires_token_and_records_failed_attempt(
    client,
    db_path,
    monkeypatch,
) -> None:
    _seed_idea(db_path)
    monkeypatch.delenv("CLICKUP_API_TOKEN", raising=False)

    response = client.post(
        "/api/v1/ideas/bu-clickup001/publish/clickup",
        json={
            "list_id": "list-123",
            "dry_run": False,
        },
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "CLICKUP_API_TOKEN is required" in detail["message"]
    assert detail["publication_attempt"]["target_type"] == "clickup_task"
    assert detail["publication_attempt"]["status"] == "failure"

    store = Store(db_path=db_path, wal_mode=True)
    try:
        attempts = store.list_publication_attempts("bu-clickup001")
        assert len(attempts) == 1
        assert attempts[0]["status"] == "failure"
        assert "CLICKUP_API_TOKEN is required" in attempts[0]["error"]
    finally:
        store.close()


def test_publish_clickup_missing_list_fails_before_network(client, db_path, monkeypatch) -> None:
    _seed_idea(db_path)
    monkeypatch.delenv("CLICKUP_LIST_ID", raising=False)

    response = client.post(
        "/api/v1/ideas/bu-clickup001/publish/clickup",
        json={"api_token": "clickup_pat", "dry_run": False},
    )

    assert response.status_code == 400
    assert "ClickUp list_id is required" in response.json()["detail"]


def test_publish_clickup_missing_idea(client, monkeypatch) -> None:
    def publisher_from_env(**kwargs):
        raise AssertionError("missing ideas should not initialize the ClickUp publisher")

    monkeypatch.setattr("max.server.api.ClickUpTaskPublisher.from_env", publisher_from_env)

    response = client.post(
        "/api/v1/ideas/missing/publish/clickup",
        json={"list_id": "list-123"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Idea not found: missing"


def test_publish_clickup_missing_evaluation(client, db_path) -> None:
    _seed_idea(db_path, with_evaluation=False)

    response = client.post(
        "/api/v1/ideas/bu-clickup001/publish/clickup",
        json={"list_id": "list-123"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Evaluation not found: bu-clickup001"


def test_publish_clickup_schema_validation(client, db_path) -> None:
    _seed_idea(db_path)

    response = client.post(
        "/api/v1/ideas/bu-clickup001/publish/clickup",
        json={
            "list_id": "list-123",
            "dry_run": True,
            "priority": 5,
        },
    )

    assert response.status_code == 422
