"""Tests for publishing ideas to Jira through the REST API."""

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
    path = str(tmp_path / "test_jira_issue_api.db")
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
                id="bu-jira001",
                title="Jira Publish Idea",
                one_liner="Publish an idea as a Jira issue",
                category=BuildableCategory.APPLICATION,
                problem="API clients cannot publish Jira issues",
                solution="Expose the Jira issue publisher over REST",
                value_proposition="Agents can publish without shelling out",
                validation_plan="Call the REST endpoint",
                domain="devtools",
                status="approved",
                evidence_rationale="Customer signals mention Jira handoff.",
                evidence_signals=["sig-jira001"],
                inspiring_insights=["ins-jira001"],
            )
        )
        if with_evaluation:
            store.insert_evaluation(_evaluation("bu-jira001"))
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


def test_publish_jira_dry_run_returns_payload_without_http(client, db_path) -> None:
    _seed_idea(db_path)

    response = client.post(
        "/api/v1/ideas/bu-jira001/publish/jira",
        json={
            "site_url": "https://example.atlassian.net",
            "project_key": "MAX",
            "issue_type": "Story",
            "labels": ["delivery"],
            "dry_run": True,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["project_key"] == "MAX"
    assert data["dry_run"] is True
    assert data["status_code"] is None
    assert data["issue_key"] is None
    assert data["issue_url"] is None
    assert data["payload"]["summary"] == "[Max] Jira Publish Idea"
    assert data["payload"]["issue_type"] == "Story"
    assert "Call the REST endpoint" in data["payload"]["description"]
    assert data["publication_attempt"]["target_type"] == "jira_issue"
    assert data["publication_attempt"]["target_url"] == (
        "https://example.atlassian.net/rest/api/3/issue"
    )
    assert data["publication_attempt"]["status"] == "success"


def test_publish_jira_live_success_records_publication_attempt(
    client,
    db_path,
    monkeypatch,
) -> None:
    _seed_idea(db_path)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json={"id": "10042", "key": "MAX-42"})

    def publisher_from_env(**kwargs):
        from max.publisher.jira_issues import JiraIssuePublisher

        return JiraIssuePublisher(
            kwargs["site_url"],
            kwargs["project_key"],
            email=kwargs["email"],
            api_token=kwargs["api_token"],
            bearer_token=kwargs["bearer_token"],
            issue_type=kwargs["issue_type"],
            labels=kwargs["labels"],
            timeout=kwargs["timeout"],
            max_retries=kwargs["max_retries"],
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

    monkeypatch.setattr("max.server.api.JiraIssuePublisher.from_env", publisher_from_env)

    response = client.post(
        "/api/v1/ideas/bu-jira001/publish/jira",
        json={
            "site_url": "https://example.atlassian.net",
            "project_key": "MAX",
            "email": "agent@example.com",
            "api_token": "jira_api_token",
            "dry_run": False,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["dry_run"] is False
    assert data["status_code"] == 201
    assert data["issue_key"] == "MAX-42"
    assert data["issue_url"] == "https://example.atlassian.net/browse/MAX-42"
    assert data["publication_attempt"]["target_type"] == "jira_issue"
    assert data["publication_attempt"]["target_url"] == data["issue_url"]
    assert data["publication_attempt"]["status"] == "success"
    assert data["publication_attempt"]["response_status"] == 201
    assert len(requests) == 1

    store = Store(db_path=db_path, wal_mode=True)
    try:
        attempts = store.list_publication_attempts("bu-jira001")
        assert len(attempts) == 1
        assert attempts[0]["target_type"] == "jira_issue"
        assert attempts[0]["target_url"] == data["issue_url"]
        assert attempts[0]["status"] == "success"
    finally:
        store.close()


def test_publish_jira_api_failure_records_failed_attempt_without_success(
    client,
    db_path,
    monkeypatch,
) -> None:
    _seed_idea(db_path)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            text="invalid token=jira_secret password=jira_password",
        )

    def publisher_from_env(**kwargs):
        from max.publisher.jira_issues import JiraIssuePublisher

        return JiraIssuePublisher(
            kwargs["site_url"],
            kwargs["project_key"],
            bearer_token=kwargs["bearer_token"],
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

    monkeypatch.setattr("max.server.api.JiraIssuePublisher.from_env", publisher_from_env)

    response = client.post(
        "/api/v1/ideas/bu-jira001/publish/jira",
        json={
            "site_url": "https://example.atlassian.net",
            "project_key": "MAX",
            "bearer_token": "jira_bearer",
            "dry_run": False,
        },
    )

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "Jira issue publish failed with HTTP 401" in detail["message"]
    assert "jira_secret" not in detail["message"]
    assert "jira_password" not in detail["message"]
    assert detail["publication_attempt"]["target_type"] == "jira_issue"
    assert detail["publication_attempt"]["status"] == "failure"
    assert detail["publication_attempt"]["response_status"] == 401

    store = Store(db_path=db_path, wal_mode=True)
    try:
        attempts = store.list_publication_attempts("bu-jira001")
        assert len(attempts) == 1
        assert attempts[0]["status"] == "failure"
        assert attempts[0]["status"] != "success"
        assert "jira_secret" not in attempts[0]["error"]
        assert "jira_password" not in attempts[0]["error"]
    finally:
        store.close()


def test_publish_jira_missing_idea(client, monkeypatch) -> None:
    def publisher_from_env(**kwargs):
        raise AssertionError("missing ideas should not initialize the Jira publisher")

    monkeypatch.setattr("max.server.api.JiraIssuePublisher.from_env", publisher_from_env)

    response = client.post(
        "/api/v1/ideas/missing/publish/jira",
        json={
            "site_url": "https://example.atlassian.net",
            "project_key": "MAX",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Idea not found: missing"


def test_publish_jira_missing_evaluation(client, db_path) -> None:
    _seed_idea(db_path, with_evaluation=False)

    response = client.post(
        "/api/v1/ideas/bu-jira001/publish/jira",
        json={
            "site_url": "https://example.atlassian.net",
            "project_key": "MAX",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Evaluation not found: bu-jira001"


def test_publish_jira_live_requires_auth_and_records_failed_attempt(
    client,
    db_path,
    monkeypatch,
) -> None:
    _seed_idea(db_path)
    monkeypatch.delenv("JIRA_EMAIL", raising=False)
    monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
    monkeypatch.delenv("JIRA_BEARER_TOKEN", raising=False)

    response = client.post(
        "/api/v1/ideas/bu-jira001/publish/jira",
        json={
            "site_url": "https://example.atlassian.net",
            "project_key": "MAX",
            "dry_run": False,
        },
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "Jira email/api_token or bearer_token is required" in detail["message"]
    assert detail["publication_attempt"]["target_type"] == "jira_issue"
    assert detail["publication_attempt"]["status"] == "failure"

    store = Store(db_path=db_path, wal_mode=True)
    try:
        attempts = store.list_publication_attempts("bu-jira001")
        assert len(attempts) == 1
        assert attempts[0]["status"] == "failure"
        assert "bearer_token is required" in attempts[0]["error"]
    finally:
        store.close()
