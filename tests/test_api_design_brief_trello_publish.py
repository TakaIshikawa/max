"""Tests for publishing design briefs to Trello through the REST API."""

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
    path = str(tmp_path / "test_design_brief_trello_api.db")
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
            id="bu-trello-brief",
            title="Trello Brief Source",
            one_liner="Publish design briefs to Trello",
            category=BuildableCategory.APPLICATION,
            ideation_mode=IdeationMode.DIRECT,
            problem="Design briefs stall before delivery tracking.",
            solution="Create a Trello card from the persisted brief.",
            value_proposition="Delivery handoffs stay lightweight.",
            buyer="Product lead",
            specific_user="Engineering manager",
            workflow_context="Execution planning",
            evidence_rationale="Teams requested Trello handoff.",
            domain="devtools",
        )
        store.insert_buildable_unit(unit)
        return store.insert_design_brief(
            ProjectBrief(
                title="Trello Design Brief",
                domain="devtools",
                theme="execution-handoff",
                lead=Candidate(unit=unit),
                readiness_score=84.0,
                why_this_now="Planning artifacts need direct follow-through.",
                merged_product_concept="A Trello publisher for design briefs.",
                synthesis_rationale="The source idea is ready for implementation planning.",
                mvp_scope=["Render Trello payload", "Create Trello card"],
                first_milestones=["Ship REST endpoint"],
                validation_plan="Dry run, then publish through a fake transport.",
                risks=["Incorrect Trello credentials"],
                source_idea_ids=["bu-trello-brief"],
            )
        )
    finally:
        store.close()


def test_publish_design_brief_trello_dry_run_returns_payload(
    client: TestClient,
    db_path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brief_id = _seed_design_brief(db_path)
    monkeypatch.delenv("TRELLO_KEY", raising=False)
    monkeypatch.delenv("TRELLO_TOKEN", raising=False)

    response = client.post(
        f"/api/v1/design-briefs/{brief_id}/publish/trello",
        json={
            "list_id": "list-123",
            "labels": ["label-design"],
            "member_ids": ["member-123"],
            "due": "2026-05-01",
            "position": "top",
            "dry_run": True,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["design_brief_id"] == brief_id
    assert data["list_id"] == "list-123"
    assert data["dry_run"] is True
    assert data["status_code"] is None
    assert data["card_id"] is None
    assert data["card_url"] is None
    assert data["payload"]["name"] == "[Max] Trello Design Brief"
    assert data["payload"]["idList"] == "list-123"
    assert "design-brief" in data["payload"]["labels"]
    assert "label-design" in data["payload"]["labels"]
    assert data["payload"]["member_ids"] == ["member-123"]
    assert data["payload"]["due"] == "2026-05-01"
    assert data["payload"]["pos"] == "top"
    assert "Dry run, then publish through a fake transport." in data["payload"]["desc"]
    assert "bu-trello-brief" in data["payload"]["desc"]
    assert data["payload"]["metadata"]["design_brief_id"] == brief_id
    assert data["payload"]["metadata"]["source_type"] == "design_brief"
    assert data["provider_metadata"]["readiness_score"] == 84.0
    assert data["request_summary"]["key"] is None
    assert data["publication_attempt"]["target_type"] == "trello_card"
    assert data["publication_attempt"]["idea_id"] == brief_id
    assert data["publication_attempt"]["status"] == "success"


def test_publish_design_brief_trello_live_success_posts_expected_request(
    client: TestClient,
    db_path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brief_id = _seed_design_brief(db_path)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "id": "card-brief-123",
                "url": "https://trello.com/c/cardbrief/1-trello-design-brief",
            },
        )

    def publisher_from_env(**kwargs):
        from max.publisher.trello_cards import TrelloCardPublisher

        return TrelloCardPublisher(
            kwargs["list_id"],
            key=kwargs["key"],
            token=kwargs["token"],
            api_url=kwargs["api_url"] or "https://api.trello.com/1",
            labels=kwargs["labels"],
            member_ids=kwargs["member_ids"],
            due=kwargs["due"],
            position=kwargs["position"],
            timeout=kwargs["timeout"],
            max_retries=kwargs["max_retries"],
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

    monkeypatch.setattr("max.server.api.TrelloCardPublisher.from_env", publisher_from_env)

    response = client.post(
        f"/api/v1/design-briefs/{brief_id}/publish/trello",
        json={
            "list_id": "list-123",
            "key": "trello_key",
            "token": "trello_token",
            "labels": ["label-design"],
            "member_ids": ["member-123", "member-456"],
            "due": "2026-05-01",
            "position": 42.0,
            "dry_run": False,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["dry_run"] is False
    assert data["status_code"] == 200
    assert data["card_id"] == "card-brief-123"
    assert data["card_url"] == "https://trello.com/c/cardbrief/1-trello-design-brief"
    assert data["publication_attempt"]["target_url"] == data["card_url"]
    assert data["publication_attempt"]["status"] == "success"
    assert len(requests) == 1
    posted = json.loads(requests[0].read())
    assert posted["name"] == "[Max] Trello Design Brief"
    assert posted["idList"] == "list-123"
    assert "label-design" in posted["idLabels"]
    assert posted["idMembers"] == "member-123,member-456"
    assert posted["due"] == "2026-05-01"
    assert posted["pos"] == 42.0
    assert "Source ideas: bu-trello-brief" in posted["desc"]


def test_publish_design_brief_trello_live_requires_credentials_and_records_failure(
    client: TestClient,
    db_path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brief_id = _seed_design_brief(db_path)
    monkeypatch.delenv("TRELLO_KEY", raising=False)
    monkeypatch.delenv("TRELLO_TOKEN", raising=False)

    response = client.post(
        f"/api/v1/design-briefs/{brief_id}/publish/trello",
        json={"list_id": "list-123", "dry_run": False},
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "TRELLO_KEY and TRELLO_TOKEN are required" in detail["message"]
    assert detail["publication_attempt"]["target_type"] == "trello_card"
    assert detail["publication_attempt"]["status"] == "failure"

    store = Store(db_path=db_path, wal_mode=True)
    try:
        attempts = store.list_publication_attempts(brief_id)
        assert len(attempts) == 1
        assert attempts[0]["status"] == "failure"
    finally:
        store.close()


def test_publish_design_brief_trello_missing_brief_returns_404(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def publisher_from_env(**kwargs):
        raise AssertionError("missing briefs should not initialize the Trello publisher")

    monkeypatch.setattr("max.server.api.TrelloCardPublisher.from_env", publisher_from_env)

    response = client.post(
        "/api/v1/design-briefs/dbf-missing/publish/trello",
        json={"list_id": "list-123"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Design brief not found: dbf-missing"
