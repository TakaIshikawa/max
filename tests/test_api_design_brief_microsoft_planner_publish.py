"""Tests for publishing design briefs to Microsoft Planner through the REST API."""

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
    path = str(tmp_path / "test_design_brief_microsoft_planner_api.db")
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
            id="bu-planner-brief",
            title="Planner Brief Source",
            one_liner="Publish design briefs to Planner",
            category=BuildableCategory.APPLICATION,
            ideation_mode=IdeationMode.DIRECT,
            problem="Design briefs stall before sprint planning.",
            solution="Create a Planner task from the persisted brief.",
            value_proposition="Planning handoffs stay visible.",
            buyer="Product lead",
            specific_user="Engineering manager",
            workflow_context="Execution planning",
            evidence_rationale="Teams requested Planner handoff.",
            domain="devtools",
        )
        store.insert_buildable_unit(unit)
        return store.insert_design_brief(
            ProjectBrief(
                title="Planner Design Brief",
                domain="devtools",
                theme="execution-handoff",
                lead=Candidate(unit=unit),
                readiness_score=86.0,
                why_this_now="Planning artifacts need direct follow-through.",
                merged_product_concept="A Planner task publisher for design briefs.",
                synthesis_rationale="The source idea is ready for implementation planning.",
                mvp_scope=["Render markdown", "Create Planner task"],
                first_milestones=["Ship REST endpoint"],
                validation_plan="Dry run, then create a fake transport task.",
                risks=["Incorrect Microsoft Graph credentials"],
                source_idea_ids=["bu-planner-brief", "bu-supporting-planner"],
            )
        )
    finally:
        store.close()


def test_publish_design_brief_microsoft_planner_dry_run_returns_payload_preview(
    client: TestClient,
    db_path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brief_id = _seed_design_brief(db_path)
    monkeypatch.delenv("MS_PLANNER_ACCESS_TOKEN", raising=False)

    body = {
        "plan_id": "plan-123",
        "bucket_id": "bucket-123",
        "title": "Custom Planner Brief",
        "assignee_user_id": "user-123",
        "due_date_time": "2026-05-15T09:00:00Z",
        "include_source_ids": True,
        "dry_run": True,
    }
    first = client.post(
        f"/api/v1/design-briefs/{brief_id}/publish/microsoft-planner", json=body
    )
    second = client.post(
        f"/api/v1/design-briefs/{brief_id}/publish/microsoft-planner", json=body
    )

    assert first.status_code == 200
    assert second.status_code == 200
    data = first.json()
    assert data["design_brief_id"] == brief_id
    assert data["plan_id"] == "plan-123"
    assert data["bucket_id"] == "bucket-123"
    assert data["dry_run"] is True
    assert data["status_code"] is None
    assert data["task_id"] is None
    assert data["title"] == "Custom Planner Brief"
    assert data["details_preview"] == second.json()["details_preview"]
    assert data["payload"]["planId"] == "plan-123"
    assert data["payload"]["bucketId"] == "bucket-123"
    assert data["payload"]["title"] == "Custom Planner Brief"
    assert data["payload"]["assignments"] == {
        "user-123": {"@odata.type": "microsoft.graph.plannerAssignment"}
    }
    assert data["payload"]["dueDateTime"] == "2026-05-15T09:00:00Z"
    assert data["payload"]["details"].startswith("# Custom Planner Brief")
    assert "A Planner task publisher for design briefs." in data["payload"]["details"]
    assert "## Source ID Context" in data["payload"]["details"]
    assert data["payload"]["metadata"]["source_type"] == "design_brief"
    assert data["payload"]["metadata"]["design_brief_id"] == brief_id
    assert data["payload"]["metadata"]["domain"] == "devtools"
    assert data["payload"]["metadata"]["theme"] == "execution-handoff"
    assert data["payload"]["metadata"]["source_idea_ids"] == [
        "bu-planner-brief",
        "bu-supporting-planner",
    ]
    assert data["request_summary"]["access_token"] is None
    assert data["publication_attempt"]["target_type"] == "microsoft_planner_task"
    assert data["publication_attempt"]["idea_id"] == brief_id
    assert data["publication_attempt"]["status"] == "success"


def test_publish_design_brief_microsoft_planner_live_success_with_fake_transport(
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
            json={
                "id": "task-123",
                "webUrl": "https://tasks.office.com/tenant/Home/Task/task-123",
            },
        )

    def publisher_from_env(**kwargs):
        from max.publisher.microsoft_planner_tasks import MicrosoftPlannerTaskPublisher

        return MicrosoftPlannerTaskPublisher(
            kwargs["plan_id"],
            kwargs["bucket_id"],
            access_token=kwargs["access_token"],
            api_url=kwargs["api_url"] or "https://graph.microsoft.com/v1.0",
            assignee_user_id=kwargs["assignee_user_id"],
            due_date_time=kwargs["due_date_time"],
            timeout=kwargs["timeout"],
            max_retries=kwargs["max_retries"],
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

    monkeypatch.setattr(
        "max.server.api.MicrosoftPlannerTaskPublisher.from_env",
        publisher_from_env,
    )

    response = client.post(
        f"/api/v1/design-briefs/{brief_id}/publish/microsoft-planner",
        json={
            "plan_id": "plan-123",
            "bucket_id": "bucket-123",
            "access_token": "graph_token",
            "assignee_user_id": "user-123",
            "due_date_time": "2026-05-15T09:00:00Z",
            "dry_run": False,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["dry_run"] is False
    assert data["status_code"] == 201
    assert data["task_id"] == "task-123"
    assert data["task_url"] == "https://tasks.office.com/tenant/Home/Task/task-123"
    assert data["provider_metadata"]["task_id"] == "task-123"
    assert data["request_summary"]["access_token"] == "[redacted]"
    assert "graph_token" not in response.text
    assert data["publication_attempt"]["target_url"] == data["task_url"]
    assert len(requests) == 1
    assert requests[0].headers["Authorization"] == "Bearer graph_token"

    sent = json.loads(requests[0].content)
    assert sent["title"] == "Planner Design Brief"
    assert sent["assignments"] == {
        "user-123": {"@odata.type": "microsoft.graph.plannerAssignment"}
    }
    assert sent["dueDateTime"] == "2026-05-15T09:00:00Z"
    assert sent["metadata"]["design_brief_id"] == brief_id
    assert "A Planner task publisher for design briefs." in sent["details"]

    store = Store(db_path=db_path, wal_mode=True)
    try:
        attempts = store.list_publication_attempts(brief_id)
        assert len(attempts) == 1
        assert attempts[0]["status"] == "success"
        assert attempts[0]["response_status"] == 201
    finally:
        store.close()


def test_publish_design_brief_microsoft_planner_missing_brief_returns_404(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def publisher_from_env(**kwargs):
        raise AssertionError("missing briefs should not initialize the Planner publisher")

    monkeypatch.setattr(
        "max.server.api.MicrosoftPlannerTaskPublisher.from_env",
        publisher_from_env,
    )

    response = client.post(
        "/api/v1/design-briefs/dbf-missing/publish/microsoft-planner",
        json={"plan_id": "plan-123", "bucket_id": "bucket-123"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Design brief not found: dbf-missing"


def test_publish_design_brief_microsoft_planner_live_requires_credentials_and_records_failure(
    client: TestClient,
    db_path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brief_id = _seed_design_brief(db_path)
    monkeypatch.delenv("MS_PLANNER_ACCESS_TOKEN", raising=False)

    response = client.post(
        f"/api/v1/design-briefs/{brief_id}/publish/microsoft-planner",
        json={"plan_id": "plan-123", "bucket_id": "bucket-123", "dry_run": False},
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "MS_PLANNER_ACCESS_TOKEN is required" in detail["message"]
    assert detail["request_summary"]["access_token"] is None
    assert detail["publication_attempt"]["target_type"] == "microsoft_planner_task"
    assert detail["publication_attempt"]["status"] == "failure"

    store = Store(db_path=db_path, wal_mode=True)
    try:
        attempts = store.list_publication_attempts(brief_id)
        assert len(attempts) == 1
        assert attempts[0]["status"] == "failure"
    finally:
        store.close()


def test_publish_design_brief_microsoft_planner_provider_failure_records_attempt(
    client: TestClient,
    db_path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brief_id = _seed_design_brief(db_path)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="invalid token graph_token")

    def publisher_from_env(**kwargs):
        from max.publisher.microsoft_planner_tasks import MicrosoftPlannerTaskPublisher

        return MicrosoftPlannerTaskPublisher(
            kwargs["plan_id"],
            kwargs["bucket_id"],
            access_token=kwargs["access_token"],
            max_retries=0,
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

    monkeypatch.setattr(
        "max.server.api.MicrosoftPlannerTaskPublisher.from_env",
        publisher_from_env,
    )

    response = client.post(
        f"/api/v1/design-briefs/{brief_id}/publish/microsoft-planner",
        json={
            "plan_id": "plan-123",
            "bucket_id": "bucket-123",
            "access_token": "graph_token",
            "dry_run": False,
        },
    )

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "Microsoft Planner task publish failed with HTTP 403" in detail["message"]
    assert "graph_token" not in response.text
    assert detail["publication_attempt"]["target_type"] == "microsoft_planner_task"
    assert detail["publication_attempt"]["status"] == "failure"
    assert detail["publication_attempt"]["response_status"] == 403

    store = Store(db_path=db_path, wal_mode=True)
    try:
        attempts = store.list_publication_attempts(brief_id)
        assert len(attempts) == 1
        assert attempts[0]["status"] == "failure"
        assert "graph_token" not in attempts[0]["error"]
    finally:
        store.close()
