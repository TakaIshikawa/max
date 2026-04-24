"""Tests for publishing ideas to GitLab through the REST API."""

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
    path = str(tmp_path / "test_gitlab_issue_api.db")
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
                id="bu-gitlab001",
                title="GitLab Publish Idea",
                one_liner="Publish an idea as a GitLab issue",
                category=BuildableCategory.APPLICATION,
                problem="API clients cannot publish GitLab issues",
                solution="Expose the GitLab issue publisher over REST",
                value_proposition="Agents can publish without shelling out",
                validation_plan="Call the REST endpoint",
                domain="devtools",
                status="approved",
                evidence_rationale="Customer signals mention GitLab handoff.",
                evidence_signals=["sig-gitlab001"],
                inspiring_insights=["ins-gitlab001"],
            )
        )
        if with_evaluation:
            store.insert_evaluation(_evaluation("bu-gitlab001"))
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


def test_publish_gitlab_dry_run_returns_payload_without_http(client, db_path) -> None:
    _seed_idea(db_path)

    response = client.post(
        "/api/v1/ideas/bu-gitlab001/publish/gitlab-issue",
        json={
            "base_url": "https://gitlab.example.com",
            "project_path": "group/project",
            "title": "Override title",
            "labels": ["delivery"],
            "assignee_ids": [12],
            "confidential": True,
            "dry_run": True,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["project"] == "group/project"
    assert data["dry_run"] is True
    assert data["status_code"] is None
    assert data["issue_id"] is None
    assert data["issue_iid"] is None
    assert data["issue_url"] is None
    assert data["attempts"] == 0
    assert data["payload"]["title"] == "[Max] Override title"
    assert data["payload"]["assignee_ids"] == [12]
    assert data["payload"]["confidential"] is True
    assert "Call the REST endpoint" in data["payload"]["description"]
    assert data["publication_attempt"]["target_type"] == "gitlab_issue"
    assert data["publication_attempt"]["target_url"] == (
        "https://gitlab.example.com/api/v4/projects/group%2Fproject/issues"
    )
    assert data["publication_attempt"]["status"] == "success"


def test_publish_gitlab_live_success_records_publication_attempt(
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
                "id": 10042,
                "iid": 42,
                "web_url": "https://gitlab.example.com/group/project/-/issues/42",
            },
        )

    def publisher_from_env(**kwargs):
        from max.publisher.gitlab_issues import GitLabIssuePublisher

        return GitLabIssuePublisher(
            kwargs["project_path"],
            token=kwargs["token"],
            base_url=kwargs["base_url"],
            labels=kwargs["labels"],
            assignee_ids=kwargs["assignee_ids"],
            confidential=kwargs["confidential"],
            timeout=kwargs["timeout"],
            max_retries=kwargs["max_retries"],
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

    monkeypatch.setattr("max.server.api.GitLabIssuePublisher.from_env", publisher_from_env)

    response = client.post(
        "/api/v1/ideas/bu-gitlab001/publish/gitlab-issue",
        json={
            "base_url": "https://gitlab.example.com",
            "project_path": "group/project",
            "token": "gitlab_pat",
            "dry_run": False,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["dry_run"] is False
    assert data["status_code"] == 201
    assert data["issue_id"] == 10042
    assert data["issue_iid"] == 42
    assert data["issue_url"] == "https://gitlab.example.com/group/project/-/issues/42"
    assert data["attempts"] == 1
    assert data["payload"]["metadata"]["gitlab_issue_iid"] == 42
    assert data["publication_attempt"]["target_type"] == "gitlab_issue"
    assert data["publication_attempt"]["target_url"] == data["issue_url"]
    assert data["publication_attempt"]["status"] == "success"
    assert data["publication_attempt"]["response_status"] == 201
    assert len(requests) == 1

    store = Store(db_path=db_path, wal_mode=True)
    try:
        attempts = store.list_publication_attempts("bu-gitlab001")
        assert len(attempts) == 1
        assert attempts[0]["target_type"] == "gitlab_issue"
        assert attempts[0]["target_url"] == data["issue_url"]
        assert attempts[0]["status"] == "success"
    finally:
        store.close()


def test_publish_gitlab_api_failure_records_failed_attempt_without_success(
    client,
    db_path,
    monkeypatch,
) -> None:
    _seed_idea(db_path)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            text="invalid token=gitlab_secret private_token=gitlab_private",
        )

    def publisher_from_env(**kwargs):
        from max.publisher.gitlab_issues import GitLabIssuePublisher

        return GitLabIssuePublisher(
            kwargs["project_path"],
            token=kwargs["token"],
            base_url=kwargs["base_url"],
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

    monkeypatch.setattr("max.server.api.GitLabIssuePublisher.from_env", publisher_from_env)

    response = client.post(
        "/api/v1/ideas/bu-gitlab001/publish/gitlab-issue",
        json={
            "base_url": "https://gitlab.example.com",
            "project_path": "group/project",
            "token": "gitlab_pat",
            "dry_run": False,
        },
    )

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "GitLab issue publish failed with HTTP 401" in detail["message"]
    assert "gitlab_secret" not in detail["message"]
    assert "gitlab_private" not in detail["message"]
    assert detail["publication_attempt"]["target_type"] == "gitlab_issue"
    assert detail["publication_attempt"]["status"] == "failure"
    assert detail["publication_attempt"]["response_status"] == 401

    store = Store(db_path=db_path, wal_mode=True)
    try:
        attempts = store.list_publication_attempts("bu-gitlab001")
        assert len(attempts) == 1
        assert attempts[0]["status"] == "failure"
        assert attempts[0]["status"] != "success"
        assert "gitlab_secret" not in attempts[0]["error"]
        assert "gitlab_private" not in attempts[0]["error"]
    finally:
        store.close()


def test_publish_gitlab_missing_idea(client, monkeypatch) -> None:
    def publisher_from_env(**kwargs):
        raise AssertionError("missing ideas should not initialize the GitLab publisher")

    monkeypatch.setattr("max.server.api.GitLabIssuePublisher.from_env", publisher_from_env)

    response = client.post(
        "/api/v1/ideas/missing/publish/gitlab-issue",
        json={
            "base_url": "https://gitlab.example.com",
            "project_path": "group/project",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Idea not found: missing"


def test_publish_gitlab_invalid_configuration_returns_400(client, db_path, monkeypatch) -> None:
    _seed_idea(db_path)
    monkeypatch.delenv("GITLAB_PROJECT_ID", raising=False)
    monkeypatch.delenv("GITLAB_PROJECT_PATH", raising=False)
    monkeypatch.delenv("GITLAB_PROJECT", raising=False)

    response = client.post(
        "/api/v1/ideas/bu-gitlab001/publish/gitlab-issue",
        json={
            "base_url": "https://gitlab.example.com",
            "dry_run": True,
        },
    )

    assert response.status_code == 400
    assert "GitLab project ID/path is required" in response.json()["detail"]


def test_publish_gitlab_live_requires_auth_and_records_failed_attempt(
    client,
    db_path,
    monkeypatch,
) -> None:
    _seed_idea(db_path)
    monkeypatch.delenv("GITLAB_TOKEN", raising=False)

    response = client.post(
        "/api/v1/ideas/bu-gitlab001/publish/gitlab-issue",
        json={
            "base_url": "https://gitlab.example.com",
            "project_path": "group/project",
            "dry_run": False,
        },
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "GITLAB_TOKEN is required" in detail["message"]
    assert detail["publication_attempt"]["target_type"] == "gitlab_issue"
    assert detail["publication_attempt"]["status"] == "failure"

    store = Store(db_path=db_path, wal_mode=True)
    try:
        attempts = store.list_publication_attempts("bu-gitlab001")
        assert len(attempts) == 1
        assert attempts[0]["status"] == "failure"
        assert "GITLAB_TOKEN is required" in attempts[0]["error"]
    finally:
        store.close()
