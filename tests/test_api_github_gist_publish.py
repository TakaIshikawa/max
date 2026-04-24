"""Tests for publishing ideas to GitHub Gists through the REST API."""

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
    path = str(tmp_path / "test_github_gist_api.db")
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
                id="bu-gist001",
                title="Gist Publish Idea",
                one_liner="Publish an idea as a GitHub Gist",
                category=BuildableCategory.APPLICATION,
                problem="API clients cannot publish lightweight idea artifacts",
                solution="Expose the GitHub Gist publisher over REST",
                value_proposition="Agents can publish without issue access",
                validation_plan="Call the REST endpoint",
                domain="devtools",
                status="evaluated",
            )
        )
        if with_evaluation:
            store.insert_evaluation(_evaluation("bu-gist001"))
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


def test_publish_github_gist_dry_run_records_payload_without_token(client, db_path) -> None:
    _seed_idea(db_path)

    response = client.post(
        "/api/v1/ideas/bu-gist001/publish/github-gist",
        json={
            "dry_run": True,
            "public": True,
            "filename": "gist-publish-idea.md",
            "evidence_links": ["https://example.com/evidence"],
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["dry_run"] is True
    assert data["status_code"] is None
    assert data["gist_url"] is None
    assert data["payload"]["public"] is True
    content = data["payload"]["files"]["gist-publish-idea.md"]["content"]
    assert "# Gist Publish Idea" in content
    assert "https://example.com/evidence" in content
    assert data["publication_attempt"]["target_type"] == "github_gist"
    assert data["publication_attempt"]["target_url"].endswith("/gists")
    assert data["publication_attempt"]["status"] == "success"

    store = Store(db_path=db_path, wal_mode=True)
    try:
        attempts = store.list_publication_attempts("bu-gist001")
        assert len(attempts) == 1
        assert attempts[0]["target_type"] == "github_gist"
        assert attempts[0]["status"] == "success"
    finally:
        store.close()


def test_publish_github_gist_live_success_records_publication_attempt(
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
            json={"id": "abc123", "html_url": "https://gist.github.com/example/abc123"},
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
        "/api/v1/ideas/bu-gist001/publish/github-gist",
        json={
            "token": "ghp_test",
            "api_url": "https://api.github.test",
            "dry_run": False,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["dry_run"] is False
    assert data["status_code"] == 201
    assert data["gist_url"] == "https://gist.github.com/example/abc123"
    assert data["payload"]["metadata"]["github_gist_id"] == "abc123"
    assert data["publication_attempt"]["status"] == "success"
    assert data["publication_attempt"]["response_status"] == 201
    assert len(requests) == 1

    store = Store(db_path=db_path, wal_mode=True)
    try:
        attempts = store.list_publication_attempts("bu-gist001")
        assert len(attempts) == 1
        assert attempts[0]["target_url"] == "https://gist.github.com/example/abc123"
    finally:
        store.close()


def test_publish_github_gist_missing_idea(client, monkeypatch) -> None:
    def publisher_from_env(**kwargs):
        raise AssertionError("missing ideas should not initialize the GitHub publisher")

    monkeypatch.setattr("max.server.api.GitHubGistPublisher.from_env", publisher_from_env)

    response = client.post(
        "/api/v1/ideas/missing/publish/github-gist",
        json={},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Idea not found: missing"


def test_publish_github_gist_live_requires_token_and_records_failed_attempt(
    client,
    db_path,
    monkeypatch,
) -> None:
    _seed_idea(db_path)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    response = client.post(
        "/api/v1/ideas/bu-gist001/publish/github-gist",
        json={"dry_run": False},
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "GITHUB_TOKEN is required" in detail["message"]
    assert detail["publication_attempt"]["status"] == "failure"
    assert detail["publication_attempt"]["target_type"] == "github_gist"

    store = Store(db_path=db_path, wal_mode=True)
    try:
        attempts = store.list_publication_attempts("bu-gist001")
        assert len(attempts) == 1
        assert attempts[0]["status"] == "failure"
        assert "GITHUB_TOKEN is required" in attempts[0]["error"]
    finally:
        store.close()


def test_publish_github_gist_live_failure_records_failed_attempt(
    client,
    db_path,
    monkeypatch,
) -> None:
    _seed_idea(db_path)

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
        "/api/v1/ideas/bu-gist001/publish/github-gist",
        json={
            "token": "ghp_bad",
            "dry_run": False,
        },
    )

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "bad credentials" in detail["message"]
    assert detail["publication_attempt"]["target_type"] == "github_gist"
    assert detail["publication_attempt"]["status"] == "failure"
    assert detail["publication_attempt"]["response_status"] == 403
