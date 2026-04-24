"""Tests for publishing ideas to GitHub Issues through the REST API."""

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
    path = str(tmp_path / "test_github_issue_api.db")
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
                id="bu-gh001",
                title="GitHub Publish Idea",
                one_liner="Publish an idea as a GitHub issue",
                category=BuildableCategory.APPLICATION,
                problem="API clients cannot publish issues",
                solution="Expose the GitHub issue publisher over REST",
                value_proposition="Agents can publish without shelling out",
                validation_plan="Call the REST endpoint",
                domain="devtools",
                status="evaluated",
            )
        )
        if with_evaluation:
            store.insert_evaluation(_evaluation("bu-gh001"))
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


def test_publish_github_issue_dry_run_records_payload_without_token(client, db_path) -> None:
    _seed_idea(db_path)

    response = client.post(
        "/api/v1/ideas/bu-gh001/publish/github-issue",
        json={
            "repository": "example/max",
            "dry_run": True,
            "labels": ["agent handoff", "tact-spec"],
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["repository"] == "example/max"
    assert data["dry_run"] is True
    assert data["status_code"] is None
    assert data["issue_url"] is None
    assert data["payload"]["title"] == "[Max] GitHub Publish Idea"
    assert "agent-handoff" in data["payload"]["labels"]
    assert data["publication_attempt"]["target_type"] == "github_issue"
    assert data["publication_attempt"]["target_url"].endswith("/repos/example/max/issues")
    assert data["publication_attempt"]["status"] == "success"

    store = Store(db_path=db_path, wal_mode=True)
    try:
        attempts = store.list_publication_attempts("bu-gh001")
        assert len(attempts) == 1
        assert attempts[0]["target_type"] == "github_issue"
        assert attempts[0]["status"] == "success"
    finally:
        store.close()


def test_publish_github_issue_live_success_records_publication_attempt(
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
            json={"html_url": "https://github.com/example/max/issues/42", "number": 42},
        )

    def publisher_from_env(**kwargs):
        from max.publisher.github_issues import GitHubIssuePublisher

        return GitHubIssuePublisher(
            kwargs["repository"],
            token=kwargs["token"],
            api_url=kwargs["api_url"] or "https://api.github.test",
            labels=kwargs["labels"],
            timeout=kwargs["timeout"],
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

    monkeypatch.setattr("max.server.api.GitHubIssuePublisher.from_env", publisher_from_env)

    response = client.post(
        "/api/v1/ideas/bu-gh001/publish/github-issue",
        json={
            "repository": "example/max",
            "token": "ghp_test",
            "api_url": "https://api.github.test",
            "dry_run": False,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["dry_run"] is False
    assert data["status_code"] == 201
    assert data["issue_url"] == "https://github.com/example/max/issues/42"
    assert data["payload"]["metadata"]["github_issue_number"] == 42
    assert data["publication_attempt"]["status"] == "success"
    assert data["publication_attempt"]["response_status"] == 201
    assert len(requests) == 1

    store = Store(db_path=db_path, wal_mode=True)
    try:
        attempts = store.list_publication_attempts("bu-gh001")
        assert len(attempts) == 1
        assert attempts[0]["target_url"] == "https://github.com/example/max/issues/42"
    finally:
        store.close()


def test_publish_github_issue_missing_idea(client, monkeypatch) -> None:
    def publisher_from_env(**kwargs):
        raise AssertionError("missing ideas should not initialize the GitHub publisher")

    monkeypatch.setattr("max.server.api.GitHubIssuePublisher.from_env", publisher_from_env)

    response = client.post(
        "/api/v1/ideas/missing/publish/github-issue",
        json={"repository": "example/max"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Idea not found: missing"


def test_publish_github_issue_missing_evaluation(client, db_path) -> None:
    _seed_idea(db_path, with_evaluation=False)

    response = client.post(
        "/api/v1/ideas/bu-gh001/publish/github-issue",
        json={"repository": "example/max"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Evaluation not found: bu-gh001"


def test_publish_github_issue_missing_repository(client, db_path, monkeypatch) -> None:
    _seed_idea(db_path)
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)

    response = client.post(
        "/api/v1/ideas/bu-gh001/publish/github-issue",
        json={"dry_run": True},
    )

    assert response.status_code == 400
    assert "GitHub repository is required" in response.json()["detail"]


def test_publish_github_issue_live_requires_token_and_records_failed_attempt(
    client,
    db_path,
    monkeypatch,
) -> None:
    _seed_idea(db_path)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    response = client.post(
        "/api/v1/ideas/bu-gh001/publish/github-issue",
        json={
            "repository": "example/max",
            "dry_run": False,
        },
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "GITHUB_TOKEN is required" in detail["message"]
    assert detail["publication_attempt"]["status"] == "failure"
    assert detail["publication_attempt"]["target_type"] == "github_issue"

    store = Store(db_path=db_path, wal_mode=True)
    try:
        attempts = store.list_publication_attempts("bu-gh001")
        assert len(attempts) == 1
        assert attempts[0]["status"] == "failure"
        assert "GITHUB_TOKEN is required" in attempts[0]["error"]
    finally:
        store.close()


def test_publish_github_issue_live_failure_records_failed_attempt(
    client,
    db_path,
    monkeypatch,
) -> None:
    _seed_idea(db_path)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="bad credentials")

    def publisher_from_env(**kwargs):
        from max.publisher.github_issues import GitHubIssuePublisher

        return GitHubIssuePublisher(
            kwargs["repository"],
            token=kwargs["token"],
            api_url=kwargs["api_url"] or "https://api.github.test",
            labels=kwargs["labels"],
            timeout=kwargs["timeout"],
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

    monkeypatch.setattr("max.server.api.GitHubIssuePublisher.from_env", publisher_from_env)

    response = client.post(
        "/api/v1/ideas/bu-gh001/publish/github-issue",
        json={
            "repository": "example/max",
            "token": "ghp_bad",
            "dry_run": False,
        },
    )

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "bad credentials" in detail["message"]
    assert detail["publication_attempt"]["target_type"] == "github_issue"
    assert detail["publication_attempt"]["status"] == "failure"
    assert detail["publication_attempt"]["response_status"] == 403

    store = Store(db_path=db_path, wal_mode=True)
    try:
        attempts = store.list_publication_attempts("bu-gh001")
        assert len(attempts) == 1
        assert attempts[0]["status"] == "failure"
        assert attempts[0]["response_status"] == 403
    finally:
        store.close()
