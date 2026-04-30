"""Tests for publishing design briefs to Jira through the REST API."""

from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.server.app import create_app
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode


@pytest.fixture
def db_path(tmp_path) -> str:
    path = str(tmp_path / "test_design_brief_jira_api.db")
    Store(db_path=path, wal_mode=True).close()
    return path


@pytest.fixture
def client(db_path: str) -> TestClient:
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


def _seed_design_brief(db_path: str) -> str:
    store = Store(db_path=db_path, wal_mode=True)
    try:
        unit = BuildableUnit(
            id="bu-jira-brief",
            title="Jira Brief Source",
            one_liner="Publish design briefs to Jira",
            category=BuildableCategory.APPLICATION,
            ideation_mode=IdeationMode.DIRECT,
            problem="Design briefs stall before sprint planning.",
            solution="Create a Jira issue from the persisted brief.",
            value_proposition="Planning handoffs stay visible.",
            buyer="Product lead",
            specific_user="Engineering manager",
            workflow_context="Execution planning",
            evidence_rationale="Teams requested Jira handoff.",
            domain="devtools",
        )
        store.insert_buildable_unit(unit)
        return store.insert_design_brief(
            ProjectBrief(
                title="Jira Design Brief",
                domain="devtools",
                theme="execution-handoff",
                lead=Candidate(unit=unit),
                readiness_score=86.0,
                why_this_now="Planning artifacts need direct follow-through.",
                merged_product_concept="A Jira issue publisher for design briefs.",
                synthesis_rationale="The source idea is ready for implementation planning.",
                mvp_scope=["Render markdown", "Create Jira issue"],
                first_milestones=["Ship REST endpoint"],
                validation_plan="Dry run, then create a fake transport issue.",
                risks=["Incorrect Jira credentials"],
                source_idea_ids=["bu-jira-brief", "bu-supporting-jira"],
            )
        )
    finally:
        store.close()


def test_publish_design_brief_jira_dry_run_returns_payload_preview(
    client: TestClient,
    db_path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brief_id = _seed_design_brief(db_path)
    monkeypatch.delenv("JIRA_EMAIL", raising=False)
    monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
    monkeypatch.delenv("JIRA_BEARER_TOKEN", raising=False)

    body = {
        "site_url": "https://example.atlassian.net",
        "project_key": "MAX",
        "issue_type": "Story",
        "title": "Custom Jira Brief",
        "labels": ["design", "execution"],
        "assignee_account_id": "acct-123",
        "priority": "High",
        "include_source_ids": True,
        "dry_run": True,
    }
    first = client.post(f"/api/v1/design-briefs/{brief_id}/publish/jira", json=body)
    second = client.post(f"/api/v1/design-briefs/{brief_id}/publish/jira", json=body)

    assert first.status_code == 200
    assert second.status_code == 200
    data = first.json()
    assert data["design_brief_id"] == brief_id
    assert data["project_key"] == "MAX"
    assert data["dry_run"] is True
    assert data["status_code"] is None
    assert data["issue_key"] is None
    assert data["summary"] == "Custom Jira Brief"
    assert data["description_preview"] == second.json()["description_preview"]
    assert data["payload"]["description"].startswith("# Custom Jira Brief")
    assert "A Jira issue publisher for design briefs." in data["payload"]["description"]
    assert "## Source ID Context" in data["payload"]["description"]
    assert data["payload"]["metadata"]["design_brief_id"] == brief_id
    assert data["labels"] == ["design", "execution"]
    assert data["assignee_account_id"] == "acct-123"
    assert data["priority"] == "High"
    assert data["provider_metadata"]["issue_endpoint"] == (
        "https://example.atlassian.net/rest/api/3/issue"
    )
    assert data["request_summary"]["api_token"] is None
    assert data["request_summary"]["bearer_token"] is None
    assert data["publication_attempt"]["target_type"] == "jira_issue"
    assert data["publication_attempt"]["idea_id"] == brief_id
    assert data["publication_attempt"]["status"] == "success"


def test_publish_design_brief_jira_live_success_with_fake_transport(
    client: TestClient,
    db_path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brief_id = _seed_design_brief(db_path)
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
            assignee_account_id=kwargs["assignee_account_id"],
            priority=kwargs["priority"],
            timeout=kwargs["timeout"],
            max_retries=kwargs["max_retries"],
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

    monkeypatch.setattr("max.server.api.JiraIssuePublisher.from_env", publisher_from_env)

    response = client.post(
        f"/api/v1/design-briefs/{brief_id}/publish/jira",
        json={
            "site_url": "https://example.atlassian.net",
            "project_key": "MAX",
            "email": "agent@example.com",
            "api_token": "jira_api_token",
            "labels": ["design"],
            "assignee_account_id": "acct-123",
            "priority": "High",
            "dry_run": False,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["dry_run"] is False
    assert data["status_code"] == 201
    assert data["issue_key"] == "MAX-42"
    assert data["issue_url"] == "https://example.atlassian.net/browse/MAX-42"
    assert data["provider_metadata"]["jira_issue_id"] == "10042"
    assert data["provider_metadata"]["jira_issue_key"] == "MAX-42"
    assert data["request_summary"]["api_token"] == "[redacted]"
    assert "jira_api_token" not in response.text
    assert data["publication_attempt"]["target_url"] == data["issue_url"]
    assert len(requests) == 1

    issue_fields = json.loads(requests[0].content)["fields"]
    assert issue_fields["project"] == {"key": "MAX"}
    assert issue_fields["issuetype"] == {"name": "Task"}
    assert issue_fields["summary"] == "Jira Design Brief"
    assert issue_fields["labels"] == ["design"]
    assert issue_fields["assignee"] == {"accountId": "acct-123"}
    assert issue_fields["priority"] == {"name": "High"}
    assert "A Jira issue publisher for design briefs." in requests[0].content.decode()

    store = Store(db_path=db_path, wal_mode=True)
    try:
        attempts = store.list_publication_attempts(brief_id)
        assert len(attempts) == 1
        assert attempts[0]["status"] == "success"
        assert attempts[0]["response_status"] == 201
    finally:
        store.close()


def test_publish_design_brief_jira_missing_brief_returns_404(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def publisher_from_env(**kwargs):
        raise AssertionError("missing briefs should not initialize the Jira publisher")

    monkeypatch.setattr("max.server.api.JiraIssuePublisher.from_env", publisher_from_env)

    response = client.post(
        "/api/v1/design-briefs/dbf-missing/publish/jira",
        json={"site_url": "https://example.atlassian.net", "project_key": "MAX"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Design brief not found: dbf-missing"


def test_publish_design_brief_jira_live_requires_credentials_and_records_failure(
    client: TestClient,
    db_path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brief_id = _seed_design_brief(db_path)
    monkeypatch.delenv("JIRA_EMAIL", raising=False)
    monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
    monkeypatch.delenv("JIRA_BEARER_TOKEN", raising=False)

    response = client.post(
        f"/api/v1/design-briefs/{brief_id}/publish/jira",
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
        attempts = store.list_publication_attempts(brief_id)
        assert len(attempts) == 1
        assert attempts[0]["status"] == "failure"
    finally:
        store.close()


def test_publish_design_brief_jira_invalid_request_config_returns_400(
    client: TestClient,
    db_path: str,
) -> None:
    brief_id = _seed_design_brief(db_path)

    response = client.post(
        f"/api/v1/design-briefs/{brief_id}/publish/jira",
        json={"site_url": "not-a-url", "project_key": "MAX"},
    )

    assert response.status_code == 400
    assert "absolute http(s) URL" in response.json()["detail"]


def test_publish_design_brief_jira_provider_failure_records_attempt_and_redacts_secrets(
    client: TestClient,
    db_path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brief_id = _seed_design_brief(db_path)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="invalid token=jira_secret password=jira_password")

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
        f"/api/v1/design-briefs/{brief_id}/publish/jira",
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
    assert "jira_secret" not in response.text
    assert "jira_password" not in response.text
    assert "jira_bearer" not in response.text
    assert detail["publication_attempt"]["target_type"] == "jira_issue"
    assert detail["publication_attempt"]["status"] == "failure"
    assert detail["publication_attempt"]["response_status"] == 401

    store = Store(db_path=db_path, wal_mode=True)
    try:
        attempts = store.list_publication_attempts(brief_id)
        assert len(attempts) == 1
        assert attempts[0]["status"] == "failure"
        assert "jira_secret" not in attempts[0]["error"]
        assert "jira_password" not in attempts[0]["error"]
    finally:
        store.close()
