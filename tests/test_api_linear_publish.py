"""Tests for publishing ideas to Linear through the REST API."""

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
    path = str(tmp_path / "test_linear_issue_api.db")
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
                id="bu-linear001",
                title="Linear Publish Idea",
                one_liner="Publish an idea as a Linear issue",
                category=BuildableCategory.APPLICATION,
                problem="API clients cannot publish Linear issues",
                solution="Expose the Linear issue publisher over REST",
                value_proposition="Agents can publish without shelling out",
                validation_plan="Call the REST endpoint",
                domain="devtools",
                status="evaluated",
                evidence_rationale="Customer signals mention Linear handoff.",
                evidence_signals=["sig-linear001"],
                inspiring_insights=["ins-linear001"],
            )
        )
        if with_evaluation:
            store.insert_evaluation(_evaluation("bu-linear001"))
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


def test_publish_linear_dry_run_returns_payload_without_http(client, db_path) -> None:
    _seed_idea(db_path)

    response = client.post(
        "/api/v1/ideas/bu-linear001/publish/linear",
        json={
            "team_id": "team-123",
            "project_id": "project-123",
            "labels": ["label-1", "label-2"],
            "priority": 2,
            "dry_run": True,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["team_id"] == "team-123"
    assert data["dry_run"] is True
    assert data["status_code"] is None
    assert data["issue_url"] is None
    assert data["payload"]["title"] == "[Max] Linear Publish Idea"
    assert data["payload"]["project_id"] == "project-123"
    assert data["payload"]["label_ids"] == ["label-1", "label-2"]
    assert "Call the REST endpoint" in data["payload"]["description"]
    assert data["publication_attempt"]["target_type"] == "linear_issue"
    assert data["publication_attempt"]["target_url"] == "https://api.linear.app/graphql"
    assert data["publication_attempt"]["status"] == "success"


def test_publish_linear_live_success_records_publication_attempt(
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
                    "issueCreate": {
                        "success": True,
                        "issue": {
                            "id": "issue-123",
                            "identifier": "MAX-42",
                            "url": "https://linear.app/max/issue/MAX-42/linear-publish-idea",
                        },
                    }
                }
            },
        )

    def publisher_from_env(**kwargs):
        from max.publisher.linear_issues import LinearIssuePublisher

        return LinearIssuePublisher(
            kwargs["team_id"],
            api_key=kwargs["api_key"],
            project_id=kwargs["project_id"],
            labels=kwargs["labels"],
            priority=kwargs["priority"],
            timeout=kwargs["timeout"],
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

    monkeypatch.setattr("max.server.api.LinearIssuePublisher.from_env", publisher_from_env)

    response = client.post(
        "/api/v1/ideas/bu-linear001/publish/linear",
        json={
            "team_id": "team-123",
            "api_key": "lin_api",
            "dry_run": False,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["dry_run"] is False
    assert data["status_code"] == 200
    assert data["issue_url"] == "https://linear.app/max/issue/MAX-42/linear-publish-idea"
    assert data["publication_attempt"]["target_type"] == "linear_issue"
    assert data["publication_attempt"]["target_url"] == data["issue_url"]
    assert data["publication_attempt"]["status"] == "success"
    assert data["publication_attempt"]["response_status"] == 200
    assert len(requests) == 1

    store = Store(db_path=db_path, wal_mode=True)
    try:
        attempts = store.list_publication_attempts("bu-linear001")
        assert len(attempts) == 1
        assert attempts[0]["target_type"] == "linear_issue"
        assert attempts[0]["target_url"] == data["issue_url"]
        assert attempts[0]["status"] == "success"
    finally:
        store.close()


def test_publish_linear_graphql_failure_records_failed_attempt(
    client,
    db_path,
    monkeypatch,
) -> None:
    _seed_idea(db_path)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"errors": [{"message": "Team not found"}]})

    def publisher_from_env(**kwargs):
        from max.publisher.linear_issues import LinearIssuePublisher

        return LinearIssuePublisher(
            kwargs["team_id"],
            api_key=kwargs["api_key"],
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

    monkeypatch.setattr("max.server.api.LinearIssuePublisher.from_env", publisher_from_env)

    response = client.post(
        "/api/v1/ideas/bu-linear001/publish/linear",
        json={
            "team_id": "team-404",
            "api_key": "lin_api",
            "dry_run": False,
        },
    )

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "Team not found" in detail["message"]
    assert detail["publication_attempt"]["target_type"] == "linear_issue"
    assert detail["publication_attempt"]["status"] == "failure"
    assert detail["publication_attempt"]["response_status"] == 200

    store = Store(db_path=db_path, wal_mode=True)
    try:
        attempts = store.list_publication_attempts("bu-linear001")
        assert len(attempts) == 1
        assert attempts[0]["status"] == "failure"
        assert "Team not found" in attempts[0]["error"]
    finally:
        store.close()


def test_publish_linear_network_failure_records_failed_attempt(
    client,
    db_path,
    monkeypatch,
) -> None:
    _seed_idea(db_path)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("network unavailable", request=request)

    def publisher_from_env(**kwargs):
        from max.publisher.linear_issues import LinearIssuePublisher

        return LinearIssuePublisher(
            kwargs["team_id"],
            api_key=kwargs["api_key"],
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

    monkeypatch.setattr("max.server.api.LinearIssuePublisher.from_env", publisher_from_env)

    response = client.post(
        "/api/v1/ideas/bu-linear001/publish/linear",
        json={
            "team_id": "team-123",
            "api_key": "lin_api",
            "dry_run": False,
        },
    )

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "network unavailable" in detail["message"]
    assert detail["publication_attempt"]["target_type"] == "linear_issue"
    assert detail["publication_attempt"]["status"] == "failure"
    assert detail["publication_attempt"]["response_status"] is None


def test_publish_linear_missing_idea(client, monkeypatch) -> None:
    def publisher_from_env(**kwargs):
        raise AssertionError("missing ideas should not initialize the Linear publisher")

    monkeypatch.setattr("max.server.api.LinearIssuePublisher.from_env", publisher_from_env)

    response = client.post(
        "/api/v1/ideas/missing/publish/linear",
        json={"team_id": "team-123"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Idea not found: missing"


def test_publish_linear_missing_evaluation(client, db_path) -> None:
    _seed_idea(db_path, with_evaluation=False)

    response = client.post(
        "/api/v1/ideas/bu-linear001/publish/linear",
        json={"team_id": "team-123"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Evaluation not found: bu-linear001"


def test_publish_linear_live_requires_api_key_and_records_failed_attempt(
    client,
    db_path,
    monkeypatch,
) -> None:
    _seed_idea(db_path)
    monkeypatch.delenv("LINEAR_API_KEY", raising=False)

    response = client.post(
        "/api/v1/ideas/bu-linear001/publish/linear",
        json={
            "team_id": "team-123",
            "dry_run": False,
        },
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "LINEAR_API_KEY is required" in detail["message"]
    assert detail["publication_attempt"]["target_type"] == "linear_issue"
    assert detail["publication_attempt"]["status"] == "failure"

    store = Store(db_path=db_path, wal_mode=True)
    try:
        attempts = store.list_publication_attempts("bu-linear001")
        assert len(attempts) == 1
        assert attempts[0]["status"] == "failure"
        assert "LINEAR_API_KEY is required" in attempts[0]["error"]
    finally:
        store.close()
