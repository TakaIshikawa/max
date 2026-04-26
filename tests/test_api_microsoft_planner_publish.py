"""Tests for publishing ideas to Microsoft Planner through the REST API."""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from max.server.app import create_app
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit
from max.types.evaluation import DimensionScore, UtilityEvaluation
from max.types.signal import Signal, SignalSourceType


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "test_microsoft_planner_api.db")
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
        store.insert_signal(
            Signal(
                id="sig-planner001",
                source_type=SignalSourceType.FORUM,
                source_adapter="hackernews",
                title="Planner handoff thread",
                content="Users want Planner publication.",
                url="https://news.ycombinator.com/item?id=456",
            )
        )
        store.insert_buildable_unit(
            BuildableUnit(
                id="bu-planner001",
                title="Planner Publish Idea",
                one_liner="Publish an idea as a Microsoft Planner task",
                category=BuildableCategory.APPLICATION,
                problem="API clients cannot publish Planner tasks",
                solution="Expose the Microsoft Planner task publisher over REST",
                value_proposition="Agents can publish without shelling out",
                validation_plan="Call the REST endpoint",
                domain="devtools",
                status="approved",
                evidence_rationale="Customer signals mention Planner handoff.",
                evidence_signals=["sig-planner001"],
                inspiring_insights=["ins-planner001"],
            )
        )
        if with_evaluation:
            store.insert_evaluation(_evaluation("bu-planner001"))
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


def test_publish_microsoft_planner_dry_run_returns_payload_without_token_or_http(
    client,
    db_path,
) -> None:
    _seed_idea(db_path)

    response = client.post(
        "/api/v1/ideas/bu-planner001/publish/microsoft-planner",
        json={
            "plan_id": "plan-123",
            "bucket_id": "bucket-123",
            "assignee_user_id": "user-123",
            "dry_run": True,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["plan_id"] == "plan-123"
    assert data["bucket_id"] == "bucket-123"
    assert data["dry_run"] is True
    assert data["status_code"] is None
    assert data["task_id"] is None
    assert data["task_url"] is None
    assert data["payload"]["planId"] == "plan-123"
    assert data["payload"]["bucketId"] == "bucket-123"
    assert data["payload"]["title"] == "Planner Publish Idea"
    assert data["payload"]["assignments"] == {
        "user-123": {"@odata.type": "microsoft.graph.plannerAssignment"}
    }
    assert data["payload"]["metadata"]["idea_id"] == "bu-planner001"
    assert "Max Metadata" in data["payload"]["details"]
    assert "Call the REST endpoint" in data["payload"]["details"]
    assert "https://news.ycombinator.com/item?id=456" in data["payload"]["details"]
    assert data["publication_attempt"]["target_type"] == "microsoft_planner_task"
    assert data["publication_attempt"]["target_url"] == (
        "https://graph.microsoft.com/v1.0/planner/tasks"
    )
    assert data["publication_attempt"]["status"] == "success"


def test_publish_microsoft_planner_live_success_records_publication_attempt(
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
                "id": "task-123",
                "webUrl": "https://tasks.office.com/tenant/Home/Task/task-123",
            },
        )

    def publisher_from_env(**kwargs):
        from max.publisher.microsoft_planner_tasks import MicrosoftPlannerTaskPublisher

        return MicrosoftPlannerTaskPublisher(
            kwargs["plan_id"],
            kwargs["bucket_id"],
            access_token=kwargs["access_token"],
            api_url=kwargs["api_url"] or "https://graph.microsoft.com/v1.0",
            assignee_user_id=kwargs["assignee_user_id"],
            timeout=kwargs["timeout"],
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

    monkeypatch.setattr(
        "max.server.api.MicrosoftPlannerTaskPublisher.from_env",
        publisher_from_env,
    )

    response = client.post(
        "/api/v1/ideas/bu-planner001/publish/microsoft-planner",
        json={
            "plan_id": "plan-123",
            "bucket_id": "bucket-123",
            "access_token": "graph_token",
            "dry_run": False,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["dry_run"] is False
    assert data["status_code"] == 201
    assert data["task_id"] == "task-123"
    assert data["task_url"] == "https://tasks.office.com/tenant/Home/Task/task-123"
    assert data["publication_attempt"]["target_type"] == "microsoft_planner_task"
    assert data["publication_attempt"]["target_url"] == data["task_url"]
    assert data["publication_attempt"]["status"] == "success"
    assert data["publication_attempt"]["response_status"] == 201
    assert len(requests) == 1
    assert requests[0].headers["Authorization"] == "Bearer graph_token"

    store = Store(db_path=db_path, wal_mode=True)
    try:
        attempts = store.list_publication_attempts("bu-planner001")
        assert len(attempts) == 1
        assert attempts[0]["target_type"] == "microsoft_planner_task"
        assert attempts[0]["target_url"] == data["task_url"]
        assert attempts[0]["status"] == "success"
    finally:
        store.close()


def test_publish_microsoft_planner_missing_idea(client, monkeypatch) -> None:
    def publisher_from_env(**kwargs):
        raise AssertionError("missing ideas should not initialize the Planner publisher")

    monkeypatch.setattr(
        "max.server.api.MicrosoftPlannerTaskPublisher.from_env",
        publisher_from_env,
    )

    response = client.post(
        "/api/v1/ideas/missing/publish/microsoft-planner",
        json={"plan_id": "plan-123", "bucket_id": "bucket-123"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Idea not found: missing"


def test_publish_microsoft_planner_publisher_failure_mapping(
    client,
    db_path,
    monkeypatch,
) -> None:
    _seed_idea(db_path)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": {"message": "Forbidden"}})

    def publisher_from_env(**kwargs):
        from max.publisher.microsoft_planner_tasks import MicrosoftPlannerTaskPublisher

        return MicrosoftPlannerTaskPublisher(
            kwargs["plan_id"],
            kwargs["bucket_id"],
            access_token=kwargs["access_token"],
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

    monkeypatch.setattr(
        "max.server.api.MicrosoftPlannerTaskPublisher.from_env",
        publisher_from_env,
    )

    response = client.post(
        "/api/v1/ideas/bu-planner001/publish/microsoft-planner",
        json={
            "plan_id": "plan-123",
            "bucket_id": "bucket-123",
            "access_token": "graph_token",
            "dry_run": False,
        },
    )

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "Microsoft Planner task publish failed with HTTP 403" in detail["message"]
    assert detail["publication_attempt"]["target_type"] == "microsoft_planner_task"
    assert detail["publication_attempt"]["status"] == "failure"
    assert detail["publication_attempt"]["response_status"] == 403

    store = Store(db_path=db_path, wal_mode=True)
    try:
        attempts = store.list_publication_attempts("bu-planner001")
        assert len(attempts) == 1
        assert attempts[0]["status"] == "failure"
        assert "HTTP 403" in attempts[0]["error"]
    finally:
        store.close()


def test_publish_microsoft_planner_missing_plan_id_returns_validation_error(
    client,
    db_path,
    monkeypatch,
) -> None:
    _seed_idea(db_path)
    monkeypatch.delenv("MS_PLANNER_PLAN_ID", raising=False)

    response = client.post(
        "/api/v1/ideas/bu-planner001/publish/microsoft-planner",
        json={"bucket_id": "bucket-123", "dry_run": True},
    )

    assert response.status_code == 400
    assert "plan_id is required" in response.json()["detail"]


def test_publish_microsoft_planner_missing_bucket_id_returns_validation_error(
    client,
    db_path,
    monkeypatch,
) -> None:
    _seed_idea(db_path)
    monkeypatch.delenv("MS_PLANNER_BUCKET_ID", raising=False)

    response = client.post(
        "/api/v1/ideas/bu-planner001/publish/microsoft-planner",
        json={"plan_id": "plan-123", "dry_run": True},
    )

    assert response.status_code == 400
    assert "bucket_id is required" in response.json()["detail"]
