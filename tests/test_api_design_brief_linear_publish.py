"""Tests for publishing design briefs to Linear through the REST API."""

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
    path = str(tmp_path / "test_design_brief_linear_api.db")
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
            id="bu-linear-brief",
            title="Linear Brief Source",
            one_liner="Publish design briefs to Linear",
            category=BuildableCategory.APPLICATION,
            ideation_mode=IdeationMode.DIRECT,
            problem="Design briefs stall before execution planning.",
            solution="Create a Linear issue from the persisted brief.",
            value_proposition="Planning handoffs stay in one workflow.",
            buyer="Product lead",
            specific_user="Engineering manager",
            workflow_context="Execution planning",
            evidence_rationale="Teams requested Linear handoff.",
            domain="devtools",
        )
        store.insert_buildable_unit(unit)
        return store.insert_design_brief(
            ProjectBrief(
                title="Linear Design Brief",
                domain="devtools",
                theme="execution-handoff",
                lead=Candidate(unit=unit),
                readiness_score=82.0,
                why_this_now="Planning artifacts need direct follow-through.",
                merged_product_concept="A Linear publisher for design briefs.",
                synthesis_rationale="The source idea is ready for implementation planning.",
                mvp_scope=["Render markdown", "Create Linear issue"],
                first_milestones=["Ship REST endpoint"],
                validation_plan="Dry run, then create a fake transport issue.",
                risks=["Incorrect Linear credentials"],
                source_idea_ids=["bu-linear-brief"],
            )
        )
    finally:
        store.close()


def test_publish_design_brief_linear_dry_run_returns_deterministic_preview(
    client: TestClient,
    db_path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brief_id = _seed_design_brief(db_path)
    monkeypatch.delenv("LINEAR_API_KEY", raising=False)

    body = {
        "team_id": "team-123",
        "project_id": "project-123",
        "labels": ["label-design", "label-plan"],
        "priority": 2,
        "assignee_id": "user-123",
        "title": "Custom Linear Brief",
        "dry_run": True,
    }
    first = client.post(f"/api/v1/design-briefs/{brief_id}/publish/linear", json=body)
    second = client.post(f"/api/v1/design-briefs/{brief_id}/publish/linear", json=body)

    assert first.status_code == 200
    assert second.status_code == 200
    data = first.json()
    assert data["design_brief_id"] == brief_id
    assert data["team_id"] == "team-123"
    assert data["dry_run"] is True
    assert data["status_code"] is None
    assert data["issue_url"] is None
    assert data["payload"]["title"] == "Custom Linear Brief"
    assert data["payload"]["description"] == second.json()["payload"]["description"]
    assert data["payload"]["description"].startswith("# Custom Linear Brief")
    assert "Dry run, then create a fake transport issue." in data["payload"]["description"]
    assert data["payload"]["label_ids"] == ["label-design", "label-plan"]
    assert data["payload"]["project_id"] == "project-123"
    assert data["payload"]["assignee_id"] == "user-123"
    assert data["payload"]["metadata"]["design_brief_id"] == brief_id
    assert data["request_summary"]["api_key"] is None
    assert data["request_summary"]["assignee_id"] == "user-123"
    assert data["provider_metadata"]["graphql_endpoint"] == "https://api.linear.app/graphql"
    assert data["publication_attempt"]["target_type"] == "linear_issue"
    assert data["publication_attempt"]["idea_id"] == brief_id
    assert data["publication_attempt"]["status"] == "success"


def test_publish_design_brief_linear_missing_brief_returns_404(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def publisher_from_env(**kwargs):
        raise AssertionError("missing briefs should not initialize the Linear publisher")

    monkeypatch.setattr("max.server.api.LinearIssuePublisher.from_env", publisher_from_env)

    response = client.post(
        "/api/v1/design-briefs/dbf-missing/publish/linear",
        json={"team_id": "team-123"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Design brief not found: dbf-missing"


def test_publish_design_brief_linear_live_requires_api_key_and_records_failure(
    client: TestClient,
    db_path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brief_id = _seed_design_brief(db_path)
    monkeypatch.delenv("LINEAR_API_KEY", raising=False)
    monkeypatch.delenv("MISSING_LINEAR_KEY", raising=False)

    response = client.post(
        f"/api/v1/design-briefs/{brief_id}/publish/linear",
        json={"team_id": "team-123", "api_key_env": "MISSING_LINEAR_KEY", "dry_run": False},
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "LINEAR_API_KEY is required" in detail["message"]
    assert detail["publication_attempt"]["target_type"] == "linear_issue"
    assert detail["publication_attempt"]["status"] == "failure"
    assert "lin_api" not in response.text

    store = Store(db_path=db_path, wal_mode=True)
    try:
        attempts = store.list_publication_attempts(brief_id)
        assert len(attempts) == 1
        assert attempts[0]["status"] == "failure"
    finally:
        store.close()


def test_publish_design_brief_linear_live_success_with_fake_transport(
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
                "data": {
                    "issueCreate": {
                        "success": True,
                        "issue": {
                            "id": "issue-brief-123",
                            "identifier": "MAX-77",
                            "url": "https://linear.app/max/issue/MAX-77/linear-design-brief",
                        },
                    }
                }
            },
        )

    def publisher_from_env(**kwargs):
        from max.publisher.linear_issues import LinearIssuePublisher

        return LinearIssuePublisher(
            kwargs["team_id"],
            api_key=kwargs["api_key"],
            project_id=kwargs["project_id"],
            labels=kwargs["labels"],
            priority=kwargs["priority"],
            assignee_id=kwargs["assignee_id"],
            timeout=kwargs["timeout"],
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

    monkeypatch.setattr("max.server.api.LinearIssuePublisher.from_env", publisher_from_env)

    response = client.post(
        f"/api/v1/design-briefs/{brief_id}/publish/linear",
        json={
            "team_id": "team-123",
            "api_key": "lin_api",
            "project_id": "project-123",
            "assignee_id": "user-123",
            "labels": ["label-1"],
            "dry_run": False,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["dry_run"] is False
    assert data["status_code"] == 200
    assert data["issue_url"] == "https://linear.app/max/issue/MAX-77/linear-design-brief"
    assert data["issue_id"] == "issue-brief-123"
    assert data["provider_metadata"]["linear_issue_identifier"] == "MAX-77"
    assert data["request_summary"]["api_key"] == "[redacted]"
    assert "lin_api" not in response.text
    assert data["publication_attempt"]["target_url"] == data["issue_url"]
    assert len(requests) == 1

    issue_input = json.loads(requests[0].content)["variables"]["input"]
    assert issue_input["teamId"] == "team-123"
    assert issue_input["projectId"] == "project-123"
    assert issue_input["assigneeId"] == "user-123"
    assert issue_input["labelIds"] == ["label-1"]
    assert issue_input["title"] == "[Max] Linear Design Brief"
    assert "A Linear publisher for design briefs." in issue_input["description"]


def test_publish_design_brief_linear_records_successful_publication_attempt(
    client: TestClient,
    db_path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brief_id = _seed_design_brief(db_path)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": {
                    "issueCreate": {
                        "success": True,
                        "issue": {"id": "issue-123", "identifier": "MAX-78"},
                    }
                }
            },
        )

    def publisher_from_env(**kwargs):
        from max.publisher.linear_issues import LinearIssuePublisher

        return LinearIssuePublisher(
            kwargs["team_id"],
            api_key=kwargs["api_key"],
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

    monkeypatch.setattr("max.server.api.LinearIssuePublisher.from_env", publisher_from_env)

    response = client.post(
        f"/api/v1/design-briefs/{brief_id}/publish/linear",
        json={"team_id": "team-123", "api_key": "lin_api", "dry_run": False},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["publication_attempt"]["target_url"] == "https://api.linear.app/graphql"

    store = Store(db_path=db_path, wal_mode=True)
    try:
        attempts = store.list_publication_attempts(brief_id)
        assert len(attempts) == 1
        assert attempts[0]["idea_id"] == brief_id
        assert attempts[0]["target_type"] == "linear_issue"
        assert attempts[0]["status"] == "success"
        assert attempts[0]["response_status"] == 200
    finally:
        store.close()
