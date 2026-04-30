"""Tests for publishing ideas to GitHub Projects through the REST API."""

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
    path = str(tmp_path / "test_github_projects_api.db")
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
                id="bu-project001",
                title="Projects Publish Idea",
                one_liner="Publish an idea as a GitHub Projects item",
                category=BuildableCategory.APPLICATION,
                problem="API clients cannot hand off ideas to GitHub Projects",
                solution="Expose the GitHub Projects publisher over REST",
                value_proposition="Agents can publish execution handoffs without shelling out",
                validation_plan="Call the REST endpoint",
                domain="devtools",
                status="approved",
                evidence_rationale="Planning teams triage in GitHub Projects.",
                evidence_signals=["sig-project001"],
                inspiring_insights=["ins-project001"],
            )
        )
        if with_evaluation:
            store.insert_evaluation(_evaluation("bu-project001"))
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


def test_publish_github_projects_dry_run_returns_payload_preview(client, db_path) -> None:
    _seed_idea(db_path)

    response = client.post(
        "/api/v1/ideas/bu-project001/publish/github-projects",
        json={
            "project_id": "PVT_kwDOProject",
            "api_url": "https://api.github.test/graphql",
            "dry_run": True,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["idea_id"] == "bu-project001"
    assert data["project_id"] == "PVT_kwDOProject"
    assert data["dry_run"] is True
    assert data["status_code"] is None
    assert data["item_id"] is None
    assert data["item_url"] is None
    assert data["payload"]["project_id"] == "PVT_kwDOProject"
    assert data["payload"]["title"] == "[Max] Projects Publish Idea"
    assert "Call the REST endpoint" in data["payload"]["body"]
    assert data["payload"]["metadata"]["publisher"] == "max.github_projects"
    assert data["payload"]["metadata"]["idea_id"] == "bu-project001"
    assert data["publication_attempt"]["target_type"] == "github_project_item"
    assert data["publication_attempt"]["target_url"] == "https://api.github.test/graphql"
    assert data["publication_attempt"]["status"] == "success"


def test_publish_github_projects_live_success_records_publication_attempt(
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
                    "addProjectV2DraftIssue": {
                        "projectItem": {
                            "id": "PVTI_item123",
                            "url": "https://github.com/orgs/acme/projects/7/views/1?pane=issue&itemId=PVTI_item123",
                            "content": {"id": "DI_draft123", "title": "[Max] Projects Publish Idea"},
                        }
                    }
                }
            },
        )

    def publisher_from_env(**kwargs):
        from max.publisher.github_projects import GitHubProjectItemPublisher

        return GitHubProjectItemPublisher(
            kwargs["project_id"],
            token=kwargs["token"],
            api_url=kwargs["api_url"] or "https://api.github.test/graphql",
            timeout=kwargs["timeout"],
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

    monkeypatch.setattr("max.server.api.GitHubProjectItemPublisher.from_env", publisher_from_env)

    response = client.post(
        "/api/v1/ideas/bu-project001/publish/github-projects",
        json={
            "project_id": "PVT_kwDOProject",
            "token": "ghp_test",
            "api_url": "https://api.github.test/graphql",
            "dry_run": False,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["dry_run"] is False
    assert data["status_code"] == 200
    assert data["item_id"] == "PVTI_item123"
    assert data["item_url"] == (
        "https://github.com/orgs/acme/projects/7/views/1?pane=issue&itemId=PVTI_item123"
    )
    assert data["payload"]["metadata"]["github_project_id"] == "PVT_kwDOProject"
    assert data["payload"]["metadata"]["github_project_item_id"] == "PVTI_item123"
    assert data["payload"]["metadata"]["github_project_item_url"] == data["item_url"]
    assert data["publication_attempt"]["target_type"] == "github_project_item"
    assert data["publication_attempt"]["target_url"] == data["item_url"]
    assert data["publication_attempt"]["status"] == "success"
    assert data["publication_attempt"]["response_status"] == 200
    assert len(requests) == 1
    assert requests[0].headers["Authorization"] == "Bearer ghp_test"

    store = Store(db_path=db_path, wal_mode=True)
    try:
        attempts = store.list_publication_attempts("bu-project001")
        assert len(attempts) == 1
        assert attempts[0]["target_type"] == "github_project_item"
        assert attempts[0]["target_url"] == data["item_url"]
        assert attempts[0]["status"] == "success"
    finally:
        store.close()


def test_publish_github_projects_missing_idea_does_not_initialize_publisher(
    client,
    monkeypatch,
) -> None:
    def publisher_from_env(**kwargs):
        raise AssertionError("missing ideas should not initialize the GitHub Projects publisher")

    monkeypatch.setattr("max.server.api.GitHubProjectItemPublisher.from_env", publisher_from_env)

    response = client.post(
        "/api/v1/ideas/missing/publish/github-projects",
        json={"project_id": "PVT_kwDOProject"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Idea not found: missing"


def test_publish_github_projects_missing_evaluation_returns_404(client, db_path, monkeypatch) -> None:
    _seed_idea(db_path, with_evaluation=False)

    def publisher_from_env(**kwargs):
        raise AssertionError("missing evaluations should not initialize the GitHub Projects publisher")

    monkeypatch.setattr("max.server.api.GitHubProjectItemPublisher.from_env", publisher_from_env)

    response = client.post(
        "/api/v1/ideas/bu-project001/publish/github-projects",
        json={"project_id": "PVT_kwDOProject"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Evaluation not found: bu-project001"


def test_publish_github_projects_publisher_validation_errors(client, db_path, monkeypatch) -> None:
    _seed_idea(db_path)
    monkeypatch.delenv("GITHUB_PROJECT_ID", raising=False)

    response = client.post(
        "/api/v1/ideas/bu-project001/publish/github-projects",
        json={"dry_run": True},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "GitHub project_id is required; pass project_id or set GITHUB_PROJECT_ID"
    )

    store = Store(db_path=db_path, wal_mode=True)
    try:
        assert store.list_publication_attempts("bu-project001") == []
    finally:
        store.close()


def test_publish_github_projects_failure_records_redacted_message(
    client,
    db_path,
    monkeypatch,
) -> None:
    _seed_idea(db_path)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"errors": [{"message": "Token ghp_secret denied access to project"}]},
        )

    def publisher_from_env(**kwargs):
        from max.publisher.github_projects import GitHubProjectItemPublisher

        return GitHubProjectItemPublisher(
            kwargs["project_id"],
            token=kwargs["token"],
            api_url=kwargs["api_url"] or "https://api.github.test/graphql",
            timeout=kwargs["timeout"],
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

    monkeypatch.setattr("max.server.api.GitHubProjectItemPublisher.from_env", publisher_from_env)

    response = client.post(
        "/api/v1/ideas/bu-project001/publish/github-projects",
        json={
            "project_id": "PVT_kwDOProject",
            "token": "ghp_secret",
            "api_url": "https://api.github.test/graphql?token=ghp_secret",
            "dry_run": False,
        },
    )

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "ghp_secret" not in detail["message"]
    assert "[redacted] denied access" in detail["message"]
    assert detail["publication_attempt"]["target_type"] == "github_project_item"
    assert detail["publication_attempt"]["target_url"] == "https://api.github.test/graphql?[redacted]"
    assert detail["publication_attempt"]["status"] == "failure"
    assert detail["publication_attempt"]["response_status"] == 200

    store = Store(db_path=db_path, wal_mode=True)
    try:
        attempts = store.list_publication_attempts("bu-project001")
        assert len(attempts) == 1
        assert attempts[0]["status"] == "failure"
        assert "ghp_secret" not in attempts[0]["error"]
    finally:
        store.close()
