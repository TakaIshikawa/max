"""Tests for publishing ideas to Shortcut through the REST API."""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from max.publisher.shortcut_stories import ShortcutStoryPublisher
from max.server.app import create_app
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit
from max.types.evaluation import DimensionScore, UtilityEvaluation


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "test_shortcut_api.db")
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
                id="bu-shortcut001",
                title="Shortcut Publish Idea",
                one_liner="Publish an approved idea as a Shortcut story",
                category=BuildableCategory.APPLICATION,
                problem="Operators cannot publish Max specs to Shortcut over REST",
                solution="Expose the Shortcut story publisher through the API",
                value_proposition="Teams can route approved specs without integration scripts",
                validation_plan="Call the REST endpoint in dry-run and live modes",
                domain="devtools",
                status="approved",
                evidence_rationale="Planning teams triage implementation work in Shortcut.",
                evidence_signals=["sig-shortcut001"],
                inspiring_insights=["ins-shortcut001"],
            )
        )
        if with_evaluation:
            store.insert_evaluation(_evaluation("bu-shortcut001"))
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
        overall_score=82.0,
        recommendation="yes",
    )


def test_publish_shortcut_dry_run_returns_story_payload(
    client,
    db_path,
    monkeypatch,
) -> None:
    _seed_idea(db_path)
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry-run Shortcut publishing should not make network calls")

    def publisher_from_env(**kwargs):
        calls.append(kwargs)
        return ShortcutStoryPublisher(
            api_url=kwargs["api_url"] or "https://shortcut.test/api/v3",
            workflow_state_id=kwargs["workflow_state_id"],
            epic_id=kwargs["epic_id"],
            labels=kwargs["labels"],
            owner_ids=kwargs["owner_ids"],
            story_type=kwargs["story_type"] or "feature",
            estimate=kwargs["estimate"],
            deadline=kwargs["deadline"],
            iteration_id=kwargs["iteration_id"],
            timeout=kwargs["timeout"],
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

    monkeypatch.setattr("max.server.api.ShortcutStoryPublisher.from_env", publisher_from_env)

    response = client.post(
        "/api/v1/ideas/bu-shortcut001/publish/shortcut",
        json={
            "api_url": "https://shortcut.test/api/v3",
            "workflow_state_id": 123,
            "epic_id": 456,
            "labels": ["handoff"],
            "owner_ids": ["user-1"],
            "estimate": 5,
            "deadline": "2026-05-15",
            "iteration_id": 789,
            "dry_run": True,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert len(calls) == 1
    assert data["idea_id"] == "bu-shortcut001"
    assert data["dry_run"] is True
    assert data["status_code"] is None
    assert data["story_id"] is None
    assert data["story_url"] is None
    assert data["payload"]["name"] == "[Max] Shortcut Publish Idea"
    assert data["payload"]["workflow_state_id"] == 123
    assert data["payload"]["epic_id"] == 456
    assert data["payload"]["owner_ids"] == ["user-1"]
    assert data["payload"]["estimate"] == 5
    assert "handoff" in data["payload"]["labels"]
    assert "Call the REST endpoint" in data["payload"]["description"]
    assert data["payload"]["metadata"]["publisher"] == "max.shortcut_stories"
    assert data["payload"]["metadata"]["idea_id"] == "bu-shortcut001"
    assert data["publication_attempt"]["target_type"] == "shortcut_story"
    assert data["publication_attempt"]["target_url"] == "https://shortcut.test/api/v3/stories"
    assert data["publication_attempt"]["status"] == "success"


def test_publish_shortcut_live_success_records_publication_attempt(
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
                "id": 42,
                "app_url": "https://app.shortcut.com/acme/story/42/shortcut-publish-idea",
            },
        )

    def publisher_from_env(**kwargs):
        return ShortcutStoryPublisher(
            api_token=kwargs["api_token"],
            api_url=kwargs["api_url"] or "https://shortcut.test/api/v3",
            workflow_state_id=kwargs["workflow_state_id"],
            labels=kwargs["labels"],
            timeout=kwargs["timeout"],
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

    monkeypatch.setattr("max.server.api.ShortcutStoryPublisher.from_env", publisher_from_env)

    response = client.post(
        "/api/v1/ideas/bu-shortcut001/publish/shortcut",
        json={
            "api_token": "shortcut_secret",
            "api_url": "https://shortcut.test/api/v3",
            "workflow_state_id": 123,
            "labels": ["handoff"],
            "dry_run": False,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["dry_run"] is False
    assert data["status_code"] == 201
    assert data["story_id"] == 42
    assert data["story_url"] == "https://app.shortcut.com/acme/story/42/shortcut-publish-idea"
    assert data["payload"]["metadata"]["shortcut_story_id"] == 42
    assert data["payload"]["metadata"]["shortcut_story_url"] == data["story_url"]
    assert data["publication_attempt"]["target_type"] == "shortcut_story"
    assert data["publication_attempt"]["target_url"] == data["story_url"]
    assert data["publication_attempt"]["status"] == "success"
    assert data["publication_attempt"]["response_status"] == 201
    assert len(requests) == 1
    assert requests[0].url == "https://shortcut.test/api/v3/stories"
    assert requests[0].headers["Shortcut-Token"] == "shortcut_secret"

    store = Store(db_path=db_path, wal_mode=True)
    try:
        attempts = store.list_publication_attempts("bu-shortcut001")
        assert len(attempts) == 1
        assert attempts[0]["target_type"] == "shortcut_story"
        assert attempts[0]["target_url"] == data["story_url"]
        assert attempts[0]["status"] == "success"
    finally:
        store.close()


def test_publish_shortcut_provider_error_records_failure(
    client,
    db_path,
    monkeypatch,
) -> None:
    _seed_idea(db_path)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="token=shortcut_secret cannot create stories")

    def publisher_from_env(**kwargs):
        return ShortcutStoryPublisher(
            api_token=kwargs["api_token"],
            api_url=kwargs["api_url"] or "https://shortcut.test/api/v3",
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

    monkeypatch.setattr("max.server.api.ShortcutStoryPublisher.from_env", publisher_from_env)

    response = client.post(
        "/api/v1/ideas/bu-shortcut001/publish/shortcut",
        json={
            "api_token": "shortcut_secret",
            "api_url": "https://shortcut.test/api/v3",
            "dry_run": False,
        },
    )

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "Shortcut story publish failed with HTTP 403" in detail["message"]
    assert "shortcut_secret" not in detail["message"]
    assert detail["publication_attempt"]["target_type"] == "shortcut_story"
    assert detail["publication_attempt"]["target_url"] == "https://shortcut.test/api/v3/stories"
    assert detail["publication_attempt"]["status"] == "failure"
    assert detail["publication_attempt"]["response_status"] == 403


def test_publish_shortcut_missing_idea_does_not_initialize_publisher(
    client,
    monkeypatch,
) -> None:
    def publisher_from_env(**kwargs):
        raise AssertionError("missing ideas should not initialize the Shortcut publisher")

    monkeypatch.setattr("max.server.api.ShortcutStoryPublisher.from_env", publisher_from_env)

    response = client.post(
        "/api/v1/ideas/missing/publish/shortcut",
        json={"workflow_state_id": 123, "dry_run": True},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Idea not found: missing"


def test_publish_shortcut_generates_spec_without_evaluation(
    client,
    db_path,
    monkeypatch,
) -> None:
    _seed_idea(db_path, with_evaluation=False)

    def publisher_from_env(**kwargs):
        return ShortcutStoryPublisher(workflow_state_id=kwargs["workflow_state_id"])

    monkeypatch.setattr("max.server.api.ShortcutStoryPublisher.from_env", publisher_from_env)

    response = client.post(
        "/api/v1/ideas/bu-shortcut001/publish/shortcut",
        json={"workflow_state_id": 123, "dry_run": True},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["payload"]["metadata"]["idea_id"] == "bu-shortcut001"
    assert "Overall Score:" not in data["payload"]["description"]
