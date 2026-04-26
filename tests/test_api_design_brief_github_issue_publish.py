"""Tests for publishing design briefs to GitHub Issues through the REST API."""

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
    path = str(tmp_path / "test_design_brief_github_issue_api.db")
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
            id="bu-github-brief",
            title="GitHub Brief Source",
            one_liner="Publish design briefs to GitHub Issues",
            category=BuildableCategory.APPLICATION,
            ideation_mode=IdeationMode.DIRECT,
            problem="Design briefs stall before implementation tracking.",
            solution="Create a GitHub issue from the persisted brief.",
            value_proposition="Planning handoffs stay visible.",
            buyer="Product lead",
            specific_user="Engineering manager",
            workflow_context="Execution planning",
            evidence_rationale="Teams requested GitHub issue handoff.",
            domain="devtools",
        )
        store.insert_buildable_unit(unit)
        return store.insert_design_brief(
            ProjectBrief(
                title="GitHub Design Brief",
                domain="devtools",
                theme="execution-handoff",
                lead=Candidate(unit=unit),
                readiness_score=84.0,
                why_this_now="Planning artifacts need direct follow-through.",
                merged_product_concept="A GitHub issue publisher for design briefs.",
                synthesis_rationale="The source idea is ready for implementation planning.",
                mvp_scope=["Render markdown", "Create GitHub issue"],
                first_milestones=["Ship REST endpoint"],
                validation_plan="Dry run, then create a fake transport issue.",
                risks=["Incorrect GitHub credentials"],
                source_idea_ids=["bu-github-brief", "bu-supporting-1"],
            )
        )
    finally:
        store.close()


def test_publish_design_brief_github_issue_dry_run_returns_preview_without_network(
    client: TestClient,
    db_path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brief_id = _seed_design_brief(db_path)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry-run publishing should not call GitHub")

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

    first = client.post(
        f"/api/v1/design-briefs/{brief_id}/publish/github-issue",
        json={
            "repository": "example/max",
            "title": "Custom GitHub Brief",
            "labels": ["design", "execution"],
            "assignees": ["octocat"],
            "milestone": 3,
            "include_source_ids": True,
            "dry_run": True,
        },
    )
    second = client.post(
        f"/api/v1/design-briefs/{brief_id}/publish/github-issue",
        json={
            "repository": "example/max",
            "title": "Custom GitHub Brief",
            "labels": ["design", "execution"],
            "assignees": ["octocat"],
            "milestone": 3,
            "include_source_ids": True,
            "dry_run": True,
        },
    )

    assert first.status_code == 200
    assert second.status_code == 200
    data = first.json()
    assert data["design_brief_id"] == brief_id
    assert data["repository"] == "example/max"
    assert data["dry_run"] is True
    assert data["status_code"] is None
    assert data["issue_url"] is None
    assert data["title"] == "Custom GitHub Brief"
    assert data["body_preview"] == second.json()["body_preview"]
    assert data["labels"] == ["design", "execution"]
    assert data["assignees"] == ["octocat"]
    assert data["milestone"] == 3
    assert data["payload"]["body"].startswith("# Custom GitHub Brief")
    assert "## Source ID Context" in data["payload"]["body"]
    assert "`bu-supporting-1`" in data["payload"]["body"]
    assert data["provider_metadata"]["issue_endpoint"].endswith("/repos/example/max/issues")
    assert data["publication_attempt"]["target_type"] == "github_issue"
    assert data["publication_attempt"]["status"] == "success"
    assert data["request_summary"]["token"] is None


def test_publish_design_brief_github_issue_live_success_with_fake_transport(
    client: TestClient,
    db_path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brief_id = _seed_design_brief(db_path)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            201,
            json={"html_url": "https://github.com/example/max/issues/77", "number": 77},
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
        f"/api/v1/design-briefs/{brief_id}/publish/github-issue",
        json={
            "repository": "example/max",
            "token": "ghp_test",
            "labels": ["design"],
            "assignees": ["octocat"],
            "milestone": 3,
            "dry_run": False,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["dry_run"] is False
    assert data["status_code"] == 201
    assert data["issue_url"] == "https://github.com/example/max/issues/77"
    assert data["provider_metadata"]["github_issue_number"] == 77
    assert data["request_summary"]["token"] == "[redacted]"
    assert "ghp_test" not in response.text
    assert data["publication_attempt"]["target_url"] == data["issue_url"]
    assert len(requests) == 1

    issue_payload = json.loads(requests[0].content)
    assert issue_payload["title"] == "[Max] GitHub Design Brief"
    assert issue_payload["labels"] == ["design"]
    assert issue_payload["assignees"] == ["octocat"]
    assert issue_payload["milestone"] == 3
    assert "A GitHub issue publisher for design briefs." in issue_payload["body"]


def test_publish_design_brief_github_issue_missing_brief_returns_404(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def publisher_from_env(**kwargs):
        raise AssertionError("missing briefs should not initialize the GitHub publisher")

    monkeypatch.setattr("max.server.api.GitHubIssuePublisher.from_env", publisher_from_env)

    response = client.post(
        "/api/v1/design-briefs/dbf-missing/publish/github-issue",
        json={"repository": "example/max"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Design brief not found: dbf-missing"


def test_publish_design_brief_github_issue_live_requires_token_and_records_failure(
    client: TestClient,
    db_path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brief_id = _seed_design_brief(db_path)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("MISSING_GITHUB_TOKEN", raising=False)

    response = client.post(
        f"/api/v1/design-briefs/{brief_id}/publish/github-issue",
        json={
            "repository": "example/max",
            "token_env": "MISSING_GITHUB_TOKEN",
            "dry_run": False,
        },
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "GITHUB_TOKEN is required" in detail["message"]
    assert detail["publication_attempt"]["target_type"] == "github_issue"
    assert detail["publication_attempt"]["status"] == "failure"

    store = Store(db_path=db_path, wal_mode=True)
    try:
        attempts = store.list_publication_attempts(brief_id)
        assert len(attempts) == 1
        assert attempts[0]["status"] == "failure"
    finally:
        store.close()


def test_publish_design_brief_github_issue_invalid_repository_returns_400(
    client: TestClient,
    db_path: str,
) -> None:
    brief_id = _seed_design_brief(db_path)

    response = client.post(
        f"/api/v1/design-briefs/{brief_id}/publish/github-issue",
        json={"repository": "not-a-repo"},
    )

    assert response.status_code == 400
    assert "owner/repo format" in response.json()["detail"]


def test_publish_design_brief_github_issue_provider_error_records_failure(
    client: TestClient,
    db_path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brief_id = _seed_design_brief(db_path)

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
        f"/api/v1/design-briefs/{brief_id}/publish/github-issue",
        json={"repository": "example/max", "token": "ghp_bad", "dry_run": False},
    )

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "bad credentials" in detail["message"]
    assert detail["publication_attempt"]["target_type"] == "github_issue"
    assert detail["publication_attempt"]["status"] == "failure"
    assert detail["publication_attempt"]["response_status"] == 403

    store = Store(db_path=db_path, wal_mode=True)
    try:
        attempts = store.list_publication_attempts(brief_id)
        assert len(attempts) == 1
        assert attempts[0]["status"] == "failure"
        assert attempts[0]["response_status"] == 403
    finally:
        store.close()
