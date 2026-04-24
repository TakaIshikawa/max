"""Tests for publishing ideas to Asana through the REST API."""

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
    path = str(tmp_path / "test_asana_task_api.db")
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
                id="bu-asana001",
                title="Asana Publish Idea",
                one_liner="Publish an idea as an Asana task",
                category=BuildableCategory.APPLICATION,
                problem="API clients cannot publish Asana tasks",
                solution="Expose the Asana task publisher over REST",
                value_proposition="Agents can publish without shelling out",
                validation_plan="Call the REST endpoint",
                domain="devtools",
                status="approved",
                evidence_rationale="Customer signals mention Asana handoff.",
                evidence_signals=["sig-asana001"],
                inspiring_insights=["ins-asana001"],
            )
        )
        if with_evaluation:
            store.insert_evaluation(_evaluation("bu-asana001"))
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


def test_publish_asana_dry_run_returns_payload_without_token_or_http(client, db_path) -> None:
    _seed_idea(db_path)

    response = client.post(
        "/api/v1/ideas/bu-asana001/publish/asana",
        json={
            "workspace_gid": "workspace-123",
            "project_gid": "project-123",
            "section_gid": "section-123",
            "assignee_gid": "user-123",
            "tags": ["tag-1", "tag-2"],
            "due_on": "2026-05-01",
            "dry_run": True,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["workspace_gid"] == "workspace-123"
    assert data["dry_run"] is True
    assert data["status_code"] is None
    assert data["task_gid"] is None
    assert data["task_url"] is None
    assert data["payload"]["data"]["name"] == "[Max] Asana Publish Idea"
    assert data["payload"]["data"]["workspace"] == "workspace-123"
    assert data["payload"]["data"]["memberships"] == [
        {"project": "project-123", "section": "section-123"}
    ]
    assert data["payload"]["data"]["assignee"] == "user-123"
    assert data["payload"]["data"]["tags"] == ["tag-1", "tag-2"]
    assert data["payload"]["data"]["due_on"] == "2026-05-01"
    assert "Call the REST endpoint" in data["payload"]["data"]["notes"]
    assert data["publication_attempt"]["target_type"] == "asana_task"
    assert data["publication_attempt"]["target_url"] == "https://app.asana.com/api/1.0/tasks"
    assert data["publication_attempt"]["status"] == "success"


def test_publish_asana_live_success_records_publication_attempt(
    client,
    db_path,
    monkeypatch,
) -> None:
    _seed_idea(db_path)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            201,
            json={
                "data": {
                    "gid": "task-123",
                    "permalink_url": "https://app.asana.com/0/project-123/task-123",
                }
            },
        )

    def publisher_from_env(**kwargs):
        from max.publisher.asana_tasks import AsanaTaskPublisher

        return AsanaTaskPublisher(
            kwargs["workspace_gid"],
            access_token=kwargs["access_token"],
            project_gid=kwargs["project_gid"],
            section_gid=kwargs["section_gid"],
            assignee_gid=kwargs["assignee_gid"],
            tags=kwargs["tags"],
            due_on=kwargs["due_on"],
            timeout=kwargs["timeout"],
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

    monkeypatch.setattr("max.server.api.AsanaTaskPublisher.from_env", publisher_from_env)

    response = client.post(
        "/api/v1/ideas/bu-asana001/publish/asana",
        json={
            "workspace_gid": "workspace-123",
            "access_token": "asana_pat",
            "project_gid": "project-123",
            "dry_run": False,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["dry_run"] is False
    assert data["status_code"] == 201
    assert data["task_gid"] == "task-123"
    assert data["task_url"] == "https://app.asana.com/0/project-123/task-123"
    assert data["publication_attempt"]["target_type"] == "asana_task"
    assert data["publication_attempt"]["target_url"] == data["task_url"]
    assert data["publication_attempt"]["status"] == "success"
    assert data["publication_attempt"]["response_status"] == 201
    assert len(requests) == 1

    store = Store(db_path=db_path, wal_mode=True)
    try:
        attempts = store.list_publication_attempts("bu-asana001")
        assert len(attempts) == 1
        assert attempts[0]["target_type"] == "asana_task"
        assert attempts[0]["target_url"] == data["task_url"]
        assert attempts[0]["status"] == "success"
    finally:
        store.close()


def test_publish_asana_http_failure_records_failed_attempt(
    client,
    db_path,
    monkeypatch,
) -> None:
    _seed_idea(db_path)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"errors": [{"message": "Forbidden"}]})

    def publisher_from_env(**kwargs):
        from max.publisher.asana_tasks import AsanaTaskPublisher

        return AsanaTaskPublisher(
            kwargs["workspace_gid"],
            access_token=kwargs["access_token"],
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

    monkeypatch.setattr("max.server.api.AsanaTaskPublisher.from_env", publisher_from_env)

    response = client.post(
        "/api/v1/ideas/bu-asana001/publish/asana",
        json={
            "workspace_gid": "workspace-123",
            "access_token": "asana_pat",
            "dry_run": False,
        },
    )

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "Asana task publish failed with HTTP 403" in detail["message"]
    assert detail["publication_attempt"]["target_type"] == "asana_task"
    assert detail["publication_attempt"]["status"] == "failure"
    assert detail["publication_attempt"]["response_status"] == 403

    store = Store(db_path=db_path, wal_mode=True)
    try:
        attempts = store.list_publication_attempts("bu-asana001")
        assert len(attempts) == 1
        assert attempts[0]["status"] == "failure"
        assert "HTTP 403" in attempts[0]["error"]
    finally:
        store.close()


def test_publish_asana_network_failure_records_failed_attempt(
    client,
    db_path,
    monkeypatch,
) -> None:
    _seed_idea(db_path)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("network unavailable", request=request)

    def publisher_from_env(**kwargs):
        from max.publisher.asana_tasks import AsanaTaskPublisher

        return AsanaTaskPublisher(
            kwargs["workspace_gid"],
            access_token=kwargs["access_token"],
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

    monkeypatch.setattr("max.server.api.AsanaTaskPublisher.from_env", publisher_from_env)

    response = client.post(
        "/api/v1/ideas/bu-asana001/publish/asana",
        json={
            "workspace_gid": "workspace-123",
            "access_token": "asana_pat",
            "dry_run": False,
        },
    )

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "network unavailable" in detail["message"]
    assert detail["publication_attempt"]["target_type"] == "asana_task"
    assert detail["publication_attempt"]["status"] == "failure"
    assert detail["publication_attempt"]["response_status"] is None


def test_publish_asana_missing_idea(client, monkeypatch) -> None:
    def publisher_from_env(**kwargs):
        raise AssertionError("missing ideas should not initialize the Asana publisher")

    monkeypatch.setattr("max.server.api.AsanaTaskPublisher.from_env", publisher_from_env)

    response = client.post(
        "/api/v1/ideas/missing/publish/asana",
        json={"workspace_gid": "workspace-123"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Idea not found: missing"


def test_publish_asana_missing_evaluation(client, db_path) -> None:
    _seed_idea(db_path, with_evaluation=False)

    response = client.post(
        "/api/v1/ideas/bu-asana001/publish/asana",
        json={"workspace_gid": "workspace-123"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Evaluation not found: bu-asana001"


def test_publish_asana_live_requires_access_token_and_records_failed_attempt(
    client,
    db_path,
    monkeypatch,
) -> None:
    _seed_idea(db_path)
    monkeypatch.delenv("ASANA_ACCESS_TOKEN", raising=False)

    response = client.post(
        "/api/v1/ideas/bu-asana001/publish/asana",
        json={
            "workspace_gid": "workspace-123",
            "dry_run": False,
        },
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "ASANA_ACCESS_TOKEN is required" in detail["message"]
    assert detail["publication_attempt"]["target_type"] == "asana_task"
    assert detail["publication_attempt"]["status"] == "failure"

    store = Store(db_path=db_path, wal_mode=True)
    try:
        attempts = store.list_publication_attempts("bu-asana001")
        assert len(attempts) == 1
        assert attempts[0]["status"] == "failure"
        assert "ASANA_ACCESS_TOKEN is required" in attempts[0]["error"]
    finally:
        store.close()


def test_publish_asana_schema_validation(client, db_path) -> None:
    _seed_idea(db_path)

    response = client.post(
        "/api/v1/ideas/bu-asana001/publish/asana",
        json={
            "workspace_gid": "workspace-123",
            "dry_run": True,
            "timeout": 0,
        },
    )

    assert response.status_code == 422
