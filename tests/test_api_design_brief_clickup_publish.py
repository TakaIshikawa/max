"""Tests for publishing design briefs to ClickUp through the REST API."""

from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.server.app import create_app
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode
from max.types.signal import Signal, SignalSourceType


@pytest.fixture
def db_path(tmp_path) -> str:
    path = str(tmp_path / "test_design_brief_clickup_api.db")
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
        store.insert_signal(
            Signal(
                id="sig-clickup-brief",
                source_type=SignalSourceType.FORUM,
                source_adapter="customer_forum",
                title="ClickUp handoff request",
                content="Design briefs should become ClickUp implementation tasks.",
                url="https://example.com/evidence/clickup-brief",
                tags=["handoff"],
                metadata={"signal_role": "solution"},
            )
        )
        unit = BuildableUnit(
            id="bu-clickup-brief",
            title="ClickUp Brief Source",
            one_liner="Publish design briefs to ClickUp",
            category=BuildableCategory.APPLICATION,
            ideation_mode=IdeationMode.DIRECT,
            problem="Design briefs stall before execution tracking.",
            solution="Create a ClickUp task from the persisted brief.",
            value_proposition="Implementation handoffs stay in ClickUp.",
            buyer="Product lead",
            specific_user="Engineering manager",
            workflow_context="Execution planning",
            evidence_rationale="Customers asked for ClickUp handoff.",
            evidence_signals=["sig-clickup-brief"],
            domain="devtools",
        )
        store.insert_buildable_unit(unit)
        return store.insert_design_brief(
            ProjectBrief(
                title="ClickUp Design Brief",
                domain="devtools",
                theme="execution-handoff",
                lead=Candidate(unit=unit),
                readiness_score=86.0,
                why_this_now="Planning artifacts need direct follow-through.",
                merged_product_concept="A ClickUp publisher for design briefs.",
                synthesis_rationale="The source idea is ready for implementation planning.",
                mvp_scope=["Render ClickUp payload", "Create ClickUp task"],
                first_milestones=["Ship REST endpoint"],
                validation_plan="Dry run, then publish through a fake transport.",
                risks=["Incorrect ClickUp credentials"],
                source_idea_ids=["bu-clickup-brief"],
            )
        )
    finally:
        store.close()


def test_publish_design_brief_clickup_dry_run_returns_payload_without_token(
    client: TestClient,
    db_path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brief_id = _seed_design_brief(db_path)
    monkeypatch.delenv("CLICKUP_API_TOKEN", raising=False)

    response = client.post(
        f"/api/v1/design-briefs/{brief_id}/publish/clickup",
        json={
            "list_id": "list-123",
            "assignees": [101, 202],
            "tags": ["handoff"],
            "priority": 2,
            "due_date": 1777593600000,
            "dry_run": True,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["design_brief_id"] == brief_id
    assert data["list_id"] == "list-123"
    assert data["dry_run"] is True
    assert data["status_code"] is None
    assert data["task_id"] is None
    assert data["payload"]["name"] == "[Max] ClickUp Design Brief"
    assert data["payload"]["list_id"] == "list-123"
    assert data["payload"]["assignees"] == [101, 202]
    assert data["payload"]["priority"] == 2
    assert data["payload"]["due_date"] == 1777593600000
    assert "design-brief" in data["payload"]["tags"]
    assert "handoff" in data["payload"]["tags"]
    assert data["payload"]["design_brief"]["summary"] == (
        "A ClickUp publisher for design briefs."
    )
    assert data["payload"]["design_brief"]["readiness_score"] == 86.0
    assert data["payload"]["design_brief"]["source_idea_ids"] == ["bu-clickup-brief"]
    assert data["payload"]["design_brief"]["evidence_links"][0]["url"] == (
        "https://example.com/evidence/clickup-brief"
    )
    assert "https://example.com/evidence/clickup-brief" in data["payload"]["description"]
    assert data["request_summary"]["api_token"] is None
    assert data["provider_metadata"]["readiness_score"] == 86.0
    assert data["publication_attempt"]["target_type"] == "clickup_task"
    assert data["publication_attempt"]["idea_id"] == brief_id
    assert data["publication_attempt"]["status"] == "success"


def test_publish_design_brief_clickup_missing_brief_returns_404(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def publisher_from_env(**kwargs):
        raise AssertionError("missing briefs should not initialize the ClickUp publisher")

    monkeypatch.setattr("max.server.api.ClickUpTaskPublisher.from_env", publisher_from_env)

    response = client.post(
        "/api/v1/design-briefs/dbf-missing/publish/clickup",
        json={"list_id": "list-123"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Design brief not found: dbf-missing"


def test_publish_design_brief_clickup_live_requires_token_and_records_failure(
    client: TestClient,
    db_path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brief_id = _seed_design_brief(db_path)
    monkeypatch.delenv("CLICKUP_API_TOKEN", raising=False)

    response = client.post(
        f"/api/v1/design-briefs/{brief_id}/publish/clickup",
        json={"list_id": "list-123", "dry_run": False},
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "CLICKUP_API_TOKEN is required" in detail["message"]
    assert detail["publication_attempt"]["target_type"] == "clickup_task"
    assert detail["publication_attempt"]["status"] == "failure"
    assert detail["request_summary"]["api_token"] is None

    store = Store(db_path=db_path, wal_mode=True)
    try:
        attempts = store.list_publication_attempts(brief_id)
        assert len(attempts) == 1
        assert attempts[0]["status"] == "failure"
    finally:
        store.close()


def test_publish_design_brief_clickup_live_success_posts_expected_request(
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
            json={"id": "task-brief-123", "url": "https://app.clickup.com/t/task-brief-123"},
        )

    def publisher_from_env(**kwargs):
        from max.publisher.clickup_tasks import ClickUpTaskPublisher

        return ClickUpTaskPublisher(
            kwargs["list_id"],
            api_token=kwargs["api_token"],
            api_url=kwargs["api_url"] or "https://api.clickup.com/api/v2",
            assignees=kwargs["assignees"],
            tags=kwargs["tags"],
            priority=kwargs["priority"],
            due_date=kwargs["due_date"],
            custom_fields=kwargs["custom_fields"],
            timeout=kwargs["timeout"],
            max_retries=kwargs["max_retries"],
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

    monkeypatch.setattr("max.server.api.ClickUpTaskPublisher.from_env", publisher_from_env)

    response = client.post(
        f"/api/v1/design-briefs/{brief_id}/publish/clickup",
        json={
            "list_id": "list-123",
            "api_token": "clickup_pat",
            "assignees": [101],
            "tags": ["handoff"],
            "priority": 3,
            "dry_run": False,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["dry_run"] is False
    assert data["status_code"] == 200
    assert data["task_id"] == "task-brief-123"
    assert data["task_url"] == "https://app.clickup.com/t/task-brief-123"
    assert data["request_summary"]["api_token"] == "[redacted]"
    assert "clickup_pat" not in response.text
    assert data["publication_attempt"]["target_url"] == data["task_url"]
    assert len(requests) == 1

    posted = json.loads(requests[0].content)
    assert posted["name"] == "[Max] ClickUp Design Brief"
    assert posted["assignees"] == [101]
    assert posted["tags"] == [
        "max",
        "tact-spec",
        "design-brief",
        "devtools",
        "candidate",
        "handoff",
    ]
    assert posted["priority"] == 3
    assert "A ClickUp publisher for design briefs." in posted["description"]
    assert "bu-clickup-brief" in posted["description"]
    assert "https://example.com/evidence/clickup-brief" in posted["description"]


def test_publish_design_brief_clickup_error_redacts_token(
    client: TestClient,
    db_path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brief_id = _seed_design_brief(db_path)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"err": "clickup_pat"})

    def publisher_from_env(**kwargs):
        from max.publisher.clickup_tasks import ClickUpTaskPublisher

        return ClickUpTaskPublisher(
            kwargs["list_id"],
            api_token=kwargs["api_token"],
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

    monkeypatch.setattr("max.server.api.ClickUpTaskPublisher.from_env", publisher_from_env)

    response = client.post(
        f"/api/v1/design-briefs/{brief_id}/publish/clickup",
        json={"list_id": "list-123", "api_token": "clickup_pat", "dry_run": False},
    )

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "ClickUp task publish failed with HTTP 403" in detail["message"]
    assert "[redacted]" in detail["message"]
    assert "clickup_pat" not in response.text
    assert detail["publication_attempt"]["target_type"] == "clickup_task"
    assert detail["publication_attempt"]["status"] == "failure"
