"""Tests for publishing design briefs to GitHub Gists through the REST API."""

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
    path = str(tmp_path / "test_design_brief_github_gist_api.db")
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
            id="bu-gist-brief",
            title="Gist Brief Source",
            one_liner="Publish design briefs to GitHub Gists",
            category=BuildableCategory.APPLICATION,
            ideation_mode=IdeationMode.DIRECT,
            problem="Design briefs need lightweight external handoff.",
            solution="Create a GitHub Gist from the persisted brief.",
            value_proposition="Planning artifacts can be shared without issue tracking.",
            buyer="Product lead",
            specific_user="Design reviewer",
            workflow_context="Design handoff",
            evidence_rationale="Teams requested lightweight Markdown exports.",
            domain="devtools",
        )
        store.insert_buildable_unit(unit)
        return store.insert_design_brief(
            ProjectBrief(
                title="Gist Design Brief",
                domain="devtools",
                theme="markdown-handoff",
                lead=Candidate(unit=unit),
                readiness_score=82.0,
                why_this_now="Teams need a quick external review artifact.",
                merged_product_concept="A GitHub Gist publisher for design briefs.",
                synthesis_rationale="The source idea is ready for design handoff.",
                mvp_scope=["Render Markdown", "Create GitHub Gist"],
                first_milestones=["Ship Gist endpoint"],
                validation_plan="Dry run, then publish with a fake transport.",
                risks=["Incorrect GitHub credentials"],
                source_idea_ids=["bu-gist-brief", "bu-supporting-gist"],
            )
        )
    finally:
        store.close()


def test_publish_design_brief_github_gist_dry_run_returns_payload_without_network(
    client: TestClient,
    db_path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brief_id = _seed_design_brief(db_path)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry-run publishing should not call GitHub")

    def publisher_from_env(**kwargs):
        from max.publisher.github_gists import GitHubGistPublisher

        return GitHubGistPublisher(
            token=kwargs["token"],
            api_url=kwargs["api_url"] or "https://api.github.test",
            public=kwargs["public"],
            filename=kwargs["filename"],
            description=kwargs["description"],
            timeout=kwargs["timeout"],
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

    monkeypatch.setattr("max.server.api.GitHubGistPublisher.from_env", publisher_from_env)

    response = client.post(
        f"/api/v1/design-briefs/{brief_id}/publish/github-gist",
        json={
            "public": True,
            "filename": "custom-design-brief.md",
            "title": "Custom Gist Brief",
            "dry_run": True,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["design_brief_id"] == brief_id
    assert data["dry_run"] is True
    assert data["status_code"] is None
    assert data["gist_url"] is None
    assert data["filename"] == "custom-design-brief.md"
    assert data["payload"]["public"] is True
    assert set(data["payload"]["files"]) == {"custom-design-brief.md"}
    content = data["payload"]["files"]["custom-design-brief.md"]["content"]
    assert content.startswith("# Custom Gist Brief")
    assert "A GitHub Gist publisher for design briefs." in content
    assert "`bu-gist-brief`" in content
    assert "`bu-supporting-gist`" in content
    assert data["payload"]["metadata"]["source_type"] == "design_brief"
    assert data["payload"]["metadata"]["design_brief_id"] == brief_id
    assert data["provider_metadata"]["gist_endpoint"].endswith("/gists")
    assert data["publication_attempt"]["target_type"] == "github_gist"
    assert data["publication_attempt"]["status"] == "success"
    assert data["request_summary"]["token"] is None

    store = Store(db_path=db_path, wal_mode=True)
    try:
        attempts = store.list_publication_attempts(brief_id)
        assert len(attempts) == 1
        assert attempts[0]["target_type"] == "github_gist"
        assert attempts[0]["status"] == "success"
    finally:
        store.close()


def test_publish_design_brief_github_gist_live_success_records_publication_attempt(
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
            json={"id": "gist123", "html_url": "https://gist.github.com/example/gist123"},
        )

    def publisher_from_env(**kwargs):
        from max.publisher.github_gists import GitHubGistPublisher

        return GitHubGistPublisher(
            token=kwargs["token"],
            api_url=kwargs["api_url"] or "https://api.github.test",
            public=kwargs["public"],
            filename=kwargs["filename"],
            description=kwargs["description"],
            timeout=kwargs["timeout"],
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

    monkeypatch.setattr("max.server.api.GitHubGistPublisher.from_env", publisher_from_env)

    response = client.post(
        f"/api/v1/design-briefs/{brief_id}/publish/github-gist",
        json={
            "token": "ghp_test",
            "api_url": "https://api.github.test",
            "public": False,
            "dry_run": False,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["dry_run"] is False
    assert data["status_code"] == 201
    assert data["gist_url"] == "https://gist.github.com/example/gist123"
    assert data["payload"]["metadata"]["github_gist_id"] == "gist123"
    assert data["request_summary"]["token"] == "[redacted]"
    assert "ghp_test" not in response.text
    assert data["publication_attempt"]["target_url"] == data["gist_url"]
    assert data["publication_attempt"]["response_status"] == 201
    assert len(requests) == 1

    posted = json.loads(requests[0].content)
    assert posted["description"] == "Max design brief: Gist Design Brief"
    assert posted["public"] is False
    assert data["filename"] in posted["files"]
    assert "# Gist Design Brief" in posted["files"][data["filename"]]["content"]
    assert "metadata" not in posted

    store = Store(db_path=db_path, wal_mode=True)
    try:
        attempts = store.list_publication_attempts(brief_id)
        assert len(attempts) == 1
        assert attempts[0]["target_url"] == "https://gist.github.com/example/gist123"
        assert attempts[0]["status"] == "success"
    finally:
        store.close()


def test_publish_design_brief_github_gist_missing_brief_returns_404(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def publisher_from_env(**kwargs):
        raise AssertionError("missing briefs should not initialize the GitHub publisher")

    monkeypatch.setattr("max.server.api.GitHubGistPublisher.from_env", publisher_from_env)

    response = client.post(
        "/api/v1/design-briefs/dbf-missing/publish/github-gist",
        json={},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Design brief not found: dbf-missing"


def test_publish_design_brief_github_gist_live_requires_token_and_records_failure(
    client: TestClient,
    db_path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brief_id = _seed_design_brief(db_path)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("MISSING_GITHUB_TOKEN", raising=False)

    response = client.post(
        f"/api/v1/design-briefs/{brief_id}/publish/github-gist",
        json={"token_env": "MISSING_GITHUB_TOKEN", "dry_run": False},
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "GITHUB_TOKEN is required" in detail["message"]
    assert detail["publication_attempt"]["target_type"] == "github_gist"
    assert detail["publication_attempt"]["status"] == "failure"

    store = Store(db_path=db_path, wal_mode=True)
    try:
        attempts = store.list_publication_attempts(brief_id)
        assert len(attempts) == 1
        assert attempts[0]["status"] == "failure"
    finally:
        store.close()


def test_publish_design_brief_github_gist_provider_error_records_failure(
    client: TestClient,
    db_path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brief_id = _seed_design_brief(db_path)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="bad credentials")

    def publisher_from_env(**kwargs):
        from max.publisher.github_gists import GitHubGistPublisher

        return GitHubGistPublisher(
            token=kwargs["token"],
            api_url=kwargs["api_url"] or "https://api.github.test",
            public=kwargs["public"],
            filename=kwargs["filename"],
            description=kwargs["description"],
            timeout=kwargs["timeout"],
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

    monkeypatch.setattr("max.server.api.GitHubGistPublisher.from_env", publisher_from_env)

    response = client.post(
        f"/api/v1/design-briefs/{brief_id}/publish/github-gist",
        json={"token": "ghp_bad", "dry_run": False},
    )

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "bad credentials" in detail["message"]
    assert detail["publication_attempt"]["target_type"] == "github_gist"
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
