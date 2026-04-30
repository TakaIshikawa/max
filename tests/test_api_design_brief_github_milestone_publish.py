"""Tests for publishing design briefs to GitHub Milestones through the REST API."""

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
    path = str(tmp_path / "test_design_brief_github_milestone_api.db")
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
            id="bu-github-milestone-brief",
            title="GitHub Milestone Brief Source",
            one_liner="Publish design briefs to GitHub Milestones",
            category=BuildableCategory.APPLICATION,
            ideation_mode=IdeationMode.DIRECT,
            problem="Design briefs can be too broad for one issue.",
            solution="Create a GitHub milestone from the persisted brief.",
            value_proposition="Planning windows stay visible.",
            buyer="Product lead",
            specific_user="Engineering manager",
            workflow_context="Delivery planning",
            evidence_rationale="Teams requested GitHub milestone handoff.",
            domain="devtools",
        )
        store.insert_buildable_unit(unit)
        return store.insert_design_brief(
            ProjectBrief(
                title="GitHub Milestone Design Brief",
                domain="devtools",
                theme="delivery-window",
                lead=Candidate(unit=unit),
                readiness_score=85.0,
                why_this_now="Planning artifacts need delivery anchors.",
                merged_product_concept="A GitHub milestone publisher for design briefs.",
                synthesis_rationale="The source idea is ready for implementation planning.",
                mvp_scope=["Render markdown", "Create GitHub milestone"],
                first_milestones=["Ship REST endpoint"],
                validation_plan="Dry run, then create a fake transport milestone.",
                risks=["Incorrect GitHub credentials"],
                source_idea_ids=["bu-github-milestone-brief", "bu-supporting-ms"],
            )
        )
    finally:
        store.close()


def test_publish_design_brief_github_milestone_dry_run_returns_preview_without_token(
    client: TestClient,
    db_path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brief_id = _seed_design_brief(db_path)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry-run publishing should not call GitHub")

    def publisher_from_env(**kwargs):
        from max.publisher.github_milestones import GitHubMilestonePublisher

        return GitHubMilestonePublisher(
            kwargs["repository"],
            token=kwargs["token"],
            api_url=kwargs["api_url"] or "https://api.github.test",
            labels=kwargs["labels"],
            timeout=kwargs["timeout"],
            max_retries=kwargs["max_retries"],
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

    monkeypatch.setattr(
        "max.server.api.GitHubMilestonePublisher.from_env",
        publisher_from_env,
    )

    body = {
        "repository": "example/max",
        "title": "Custom Milestone Brief",
        "labels": ["design", "delivery"],
        "state": "open",
        "due_on": "2026-06-01T00:00:00Z",
        "include_source_ids": True,
        "dry_run": True,
    }
    first = client.post(f"/api/v1/design-briefs/{brief_id}/publish/github-milestone", json=body)
    second = client.post(f"/api/v1/design-briefs/{brief_id}/publish/github-milestone", json=body)

    assert first.status_code == 200
    assert second.status_code == 200
    data = first.json()
    assert data["design_brief_id"] == brief_id
    assert data["repository"] == "example/max"
    assert data["dry_run"] is True
    assert data["status_code"] is None
    assert data["milestone_number"] is None
    assert data["milestone_url"] is None
    assert data["title"] == "Custom Milestone Brief"
    assert data["description_preview"] == second.json()["description_preview"]
    assert data["state"] == "open"
    assert data["due_on"] == "2026-06-01T00:00:00Z"
    assert data["labels"] == ["design", "delivery"]
    assert data["payload"]["description"].startswith("# Custom Milestone Brief")
    assert "A GitHub milestone publisher for design briefs." in data["payload"]["description"]
    assert "## Source ID Context" in data["payload"]["description"]
    assert "`bu-supporting-ms`" in data["payload"]["description"]
    assert data["payload"]["metadata"]["design_brief_id"] == brief_id
    assert data["provider_metadata"]["milestone_endpoint"].endswith(
        "/repos/example/max/milestones"
    )
    assert data["request_summary"]["token"] is None
    assert data["publication_attempt"]["target_type"] == "github_milestone"
    assert data["publication_attempt"]["idea_id"] == brief_id
    assert data["publication_attempt"]["status"] == "success"


def test_publish_design_brief_github_milestone_live_success_with_fake_transport(
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
            json={"html_url": "https://github.com/example/max/milestone/5", "number": 5},
        )

    def publisher_from_env(**kwargs):
        from max.publisher.github_milestones import GitHubMilestonePublisher

        return GitHubMilestonePublisher(
            kwargs["repository"],
            token=kwargs["token"],
            api_url=kwargs["api_url"] or "https://api.github.test",
            labels=kwargs["labels"],
            timeout=kwargs["timeout"],
            max_retries=kwargs["max_retries"],
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

    monkeypatch.setattr(
        "max.server.api.GitHubMilestonePublisher.from_env",
        publisher_from_env,
    )

    response = client.post(
        f"/api/v1/design-briefs/{brief_id}/publish/github-milestone",
        json={
            "repository": "example/max",
            "token": "ghp_test",
            "labels": ["design"],
            "due_on": "2026-06-01T00:00:00Z",
            "dry_run": False,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["dry_run"] is False
    assert data["status_code"] == 201
    assert data["milestone_number"] == 5
    assert data["milestone_url"] == "https://github.com/example/max/milestone/5"
    assert data["provider_metadata"]["github_milestone_number"] == 5
    assert data["request_summary"]["token"] == "[redacted]"
    assert "ghp_test" not in response.text
    assert data["publication_attempt"]["target_url"] == data["milestone_url"]
    assert data["publication_attempt"]["response_status"] == 201
    assert len(requests) == 1

    milestone_payload = json.loads(requests[0].content)
    assert milestone_payload["title"] == "GitHub Milestone Design Brief"
    assert milestone_payload["state"] == "open"
    assert milestone_payload["due_on"] == "2026-06-01T00:00:00Z"
    assert "labels" not in milestone_payload
    assert "metadata" not in milestone_payload
    assert "A GitHub milestone publisher for design briefs." in milestone_payload["description"]

    store = Store(db_path=db_path, wal_mode=True)
    try:
        attempts = store.list_publication_attempts(brief_id)
        assert len(attempts) == 1
        assert attempts[0]["status"] == "success"
        assert attempts[0]["response_status"] == 201
    finally:
        store.close()


def test_publish_design_brief_github_milestone_missing_brief_returns_404(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def publisher_from_env(**kwargs):
        raise AssertionError("missing briefs should not initialize the GitHub publisher")

    monkeypatch.setattr(
        "max.server.api.GitHubMilestonePublisher.from_env",
        publisher_from_env,
    )

    response = client.post(
        "/api/v1/design-briefs/dbf-missing/publish/github-milestone",
        json={"repository": "example/max"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Design brief not found: dbf-missing"


def test_publish_design_brief_github_milestone_live_requires_token_and_records_failure(
    client: TestClient,
    db_path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brief_id = _seed_design_brief(db_path)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("MISSING_GITHUB_TOKEN", raising=False)

    response = client.post(
        f"/api/v1/design-briefs/{brief_id}/publish/github-milestone",
        json={
            "repository": "example/max",
            "token_env": "MISSING_GITHUB_TOKEN",
            "dry_run": False,
        },
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "GITHUB_TOKEN is required" in detail["message"]
    assert detail["publication_attempt"]["target_type"] == "github_milestone"
    assert detail["publication_attempt"]["status"] == "failure"

    store = Store(db_path=db_path, wal_mode=True)
    try:
        attempts = store.list_publication_attempts(brief_id)
        assert len(attempts) == 1
        assert attempts[0]["status"] == "failure"
    finally:
        store.close()


def test_publish_design_brief_github_milestone_invalid_repository_returns_400(
    client: TestClient,
    db_path: str,
) -> None:
    brief_id = _seed_design_brief(db_path)

    response = client.post(
        f"/api/v1/design-briefs/{brief_id}/publish/github-milestone",
        json={"repository": "not-a-repo"},
    )

    assert response.status_code == 400
    assert "owner/repo format" in response.json()["detail"]


def test_publish_design_brief_github_milestone_provider_error_records_failure_and_redacts(
    client: TestClient,
    db_path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brief_id = _seed_design_brief(db_path)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            text="bad token=body_secret password=body_password "
            "https://api.github.test/repos/example/max/milestones?token=url_secret",
        )

    def publisher_from_env(**kwargs):
        from max.publisher.github_milestones import GitHubMilestonePublisher

        return GitHubMilestonePublisher(
            kwargs["repository"],
            token=kwargs["token"],
            api_url="https://api.github.test?token=site_secret",
            labels=kwargs["labels"],
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

    monkeypatch.setattr(
        "max.server.api.GitHubMilestonePublisher.from_env",
        publisher_from_env,
    )

    response = client.post(
        f"/api/v1/design-briefs/{brief_id}/publish/github-milestone",
        json={"repository": "example/max", "token": "ghp_bad", "dry_run": False},
    )

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "GitHub milestone publish failed with HTTP 403" in detail["message"]
    assert "body_secret" not in response.text
    assert "body_password" not in response.text
    assert "url_secret" not in response.text
    assert "site_secret" not in response.text
    assert "ghp_bad" not in response.text
    assert detail["publication_attempt"]["target_type"] == "github_milestone"
    assert detail["publication_attempt"]["status"] == "failure"
    assert detail["publication_attempt"]["response_status"] == 403

    store = Store(db_path=db_path, wal_mode=True)
    try:
        attempts = store.list_publication_attempts(brief_id)
        assert len(attempts) == 1
        assert attempts[0]["status"] == "failure"
        assert "body_secret" not in attempts[0]["error"]
        assert "body_password" not in attempts[0]["error"]
    finally:
        store.close()
