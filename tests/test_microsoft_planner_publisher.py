"""Tests for Microsoft Planner task publishing."""

from __future__ import annotations

import json

import httpx
import pytest

from max.publisher.microsoft_planner_tasks import (
    MicrosoftPlannerTaskPublishError,
    MicrosoftPlannerTaskPublisher,
)


def _tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {
            "system": "max",
            "type": "idea",
            "idea_id": "bu-planner001",
            "status": "approved",
            "domain": "devtools",
            "category": "automation",
            "created_at": "2026-04-22T00:00:00+00:00",
            "updated_at": "2026-04-22T00:00:00+00:00",
        },
        "project": {
            "title": "Planner Publish Idea",
            "summary": "Publish implementation-ready ideas to Microsoft Planner",
            "target_users": "developers",
        },
        "problem": {"statement": "Reviewed ideas are trapped in Max"},
        "solution": {"approach": "Create Planner tasks through Microsoft Graph"},
        "execution": {
            "mvp_scope": ["Planner publisher", "REST endpoint"],
            "validation_plan": "Publish one approved idea into a test plan.",
        },
        "evidence": {
            "rationale": "Teams coordinate execution in Microsoft 365.",
            "insight_ids": ["ins-planner001"],
            "signal_ids": ["sig-planner001"],
            "source_idea_ids": ["bu-source001"],
            "links": ["https://example.com/evidence"],
        },
        "quality": {
            "quality_score": 8.0,
            "novelty_score": 7.0,
            "usefulness_score": 9.0,
            "rejection_tags": [],
        },
        "evaluation": {
            "overall_score": 82.0,
            "recommendation": "yes",
            "dimensions": {},
        },
    }


def test_build_task_payload_maps_tact_spec_fields() -> None:
    publisher = MicrosoftPlannerTaskPublisher(
        "plan-123",
        "bucket-123",
        assignee_user_id="user-123",
    )

    payload = publisher.build_task_payload(_tact_spec()).to_dict()

    assert payload["planId"] == "plan-123"
    assert payload["bucketId"] == "bucket-123"
    assert payload["title"] == "Planner Publish Idea"
    assert payload["assignments"] == {
        "user-123": {"@odata.type": "microsoft.graph.plannerAssignment"}
    }
    assert payload["metadata"]["publisher"] == "max.microsoft_planner_tasks"
    assert payload["metadata"]["idea_id"] == "bu-planner001"
    assert "Max Metadata" in payload["details"]
    assert "Idea ID: bu-planner001" in payload["details"]
    assert "Reviewed ideas are trapped in Max" in payload["details"]
    assert "Create Planner tasks through Microsoft Graph" in payload["details"]
    assert "Publish one approved idea" in payload["details"]
    assert "https://example.com/evidence" in payload["details"]


def test_dry_run_returns_payload_without_token_or_network() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = MicrosoftPlannerTaskPublisher("plan-123", "bucket-123", client=client)

    result = publisher.publish(_tact_spec(), dry_run=True)

    assert result.dry_run is True
    assert result.status_code is None
    assert result.task_id is None
    assert result.task_url is None
    assert result.payload["planId"] == "plan-123"
    assert result.payload["bucketId"] == "bucket-123"
    assert result.payload["title"] == "Planner Publish Idea"
    assert result.payload["metadata"]["idea_id"] == "bu-planner001"
    assert "assignments" not in result.payload


def test_live_publish_posts_planner_task_with_bearer_auth() -> None:
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

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = MicrosoftPlannerTaskPublisher(
        "plan-123",
        "bucket-123",
        access_token="graph_token",
        assignee_user_id="user-123",
        client=client,
    )

    result = publisher.publish(_tact_spec(), dry_run=False)

    assert result.status_code == 201
    assert result.task_id == "task-123"
    assert result.task_url == "https://tasks.office.com/tenant/Home/Task/task-123"
    assert requests[0].url == "https://graph.microsoft.com/v1.0/planner/tasks"
    assert requests[0].headers["Authorization"] == "Bearer graph_token"
    posted = _json_from_request(requests[0])
    assert posted["planId"] == "plan-123"
    assert posted["bucketId"] == "bucket-123"
    assert posted["title"] == "Planner Publish Idea"
    assert posted["assignments"]["user-123"]["@odata.type"] == "microsoft.graph.plannerAssignment"
    assert "Create Planner tasks through Microsoft Graph" in posted["details"]
    assert result.payload == posted


def test_live_publish_requires_access_token() -> None:
    publisher = MicrosoftPlannerTaskPublisher("plan-123", "bucket-123")

    with pytest.raises(MicrosoftPlannerTaskPublishError, match="MS_PLANNER_ACCESS_TOKEN"):
        publisher.publish(_tact_spec(), dry_run=False)


def test_missing_plan_id_or_bucket_id_has_clear_validation_error() -> None:
    with pytest.raises(MicrosoftPlannerTaskPublishError, match="plan_id is required"):
        MicrosoftPlannerTaskPublisher("", "bucket-123")

    with pytest.raises(MicrosoftPlannerTaskPublishError, match="bucket_id is required"):
        MicrosoftPlannerTaskPublisher("plan-123", "")


def test_live_publish_raises_on_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "Unauthorized"}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = MicrosoftPlannerTaskPublisher(
        "plan-123",
        "bucket-123",
        access_token="graph_token",
        client=client,
    )

    with pytest.raises(MicrosoftPlannerTaskPublishError, match="HTTP 401") as exc:
        publisher.publish(_tact_spec(), dry_run=False)

    assert exc.value.status_code == 401


def test_from_env_reads_required_values_and_access_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MS_PLANNER_PLAN_ID", "plan-env")
    monkeypatch.setenv("MS_PLANNER_BUCKET_ID", "bucket-env")
    monkeypatch.setenv("MS_PLANNER_ACCESS_TOKEN", "token-env")
    monkeypatch.setenv("MS_PLANNER_ASSIGNEE_USER_ID", "user-env")

    publisher = MicrosoftPlannerTaskPublisher.from_env()

    assert publisher.plan_id == "plan-env"
    assert publisher.bucket_id == "bucket-env"
    assert publisher.access_token == "token-env"
    assert publisher.assignee_user_id == "user-env"


def _json_from_request(request: httpx.Request) -> dict:
    return json.loads(request.read())
