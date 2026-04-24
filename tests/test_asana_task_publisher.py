"""Tests for Asana task publishing."""

from __future__ import annotations

import json

import httpx
import pytest

from max.publisher.asana_tasks import AsanaTaskPublishError, AsanaTaskPublisher


def _tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {
            "system": "max",
            "type": "idea",
            "idea_id": "bu-asana001",
            "status": "approved",
            "domain": "devtools",
            "category": "automation",
            "created_at": "2026-04-22T00:00:00+00:00",
            "updated_at": "2026-04-22T00:00:00+00:00",
        },
        "project": {
            "title": "Asana Publish Idea",
            "summary": "Publish implementation-ready ideas to Asana",
            "target_users": "developers",
        },
        "problem": {"statement": "Reviewed ideas are trapped in Max"},
        "solution": {"approach": "Create Asana tasks through REST"},
        "execution": {
            "mvp_scope": ["Asana publisher", "REST endpoint"],
            "validation_plan": "Publish one approved idea into a test project.",
        },
        "evidence": {
            "rationale": "Teams coordinate execution in Asana.",
            "insight_ids": ["ins-asana001"],
            "signal_ids": ["sig-asana001"],
            "source_idea_ids": ["bu-source001"],
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
            "dimensions": {
                "pain_severity": {
                    "value": 8.0,
                    "confidence": 0.8,
                    "reasoning": "Manual handoff is slow.",
                },
            },
        },
    }


def test_build_task_payload_maps_tact_spec_fields() -> None:
    publisher = AsanaTaskPublisher(
        "workspace-123",
        project_gid="project-123",
        section_gid="section-123",
        assignee_gid="user-123",
        tags=["tag-1", "tag-2"],
        due_on="2026-05-01",
    )

    payload = publisher.build_task_payload(_tact_spec()).to_dict()
    data = payload["data"]

    assert data["name"] == "[Max] Asana Publish Idea"
    assert data["workspace"] == "workspace-123"
    assert data["memberships"] == [{"project": "project-123", "section": "section-123"}]
    assert data["assignee"] == "user-123"
    assert data["tags"] == ["tag-1", "tag-2"]
    assert data["due_on"] == "2026-05-01"
    assert "Idea ID: bu-asana001" in data["notes"]
    assert "Evidence Chain" in data["notes"]
    assert "Publish one approved idea" in data["notes"]
    assert "external" not in data


def test_dry_run_returns_exact_asana_payload_without_token_or_network() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = AsanaTaskPublisher(
        "workspace-123",
        project_gid="project-123",
        tags=["tag-1"],
        client=client,
    )

    result = publisher.publish(_tact_spec(), dry_run=True)

    assert result.dry_run is True
    assert result.status_code is None
    assert result.task_gid is None
    assert result.task_url is None
    assert result.payload == publisher.build_task_payload(_tact_spec()).to_dict()
    assert result.payload["data"]["projects"] == ["project-123"]


def test_live_publish_posts_asana_task() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            201,
            json={
                "data": {
                    "gid": "task-123",
                    "permalink_url": "https://app.asana.com/0/project-123/task-123",
                }
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = AsanaTaskPublisher(
        "workspace-123",
        access_token="asana_pat",
        project_gid="project-123",
        client=client,
    )

    result = publisher.publish(_tact_spec(), dry_run=False)

    assert result.status_code == 201
    assert result.task_gid == "task-123"
    assert result.task_url == "https://app.asana.com/0/project-123/task-123"
    assert requests[0].url == "https://app.asana.com/api/1.0/tasks"
    assert requests[0].headers["Authorization"] == "Bearer asana_pat"
    posted = _json_from_request(requests[0])
    assert posted["data"]["workspace"] == "workspace-123"
    assert posted["data"]["projects"] == ["project-123"]
    assert posted["data"]["name"] == "[Max] Asana Publish Idea"
    assert "Create Asana tasks through REST" in posted["data"]["notes"]
    assert result.payload == posted


def test_live_publish_requires_access_token() -> None:
    publisher = AsanaTaskPublisher("workspace-123")

    with pytest.raises(AsanaTaskPublishError, match="ASANA_ACCESS_TOKEN is required"):
        publisher.publish(_tact_spec(), dry_run=False)


def test_live_publish_raises_on_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"errors": [{"message": "Not Authorized"}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = AsanaTaskPublisher("workspace-123", access_token="asana_pat", client=client)

    with pytest.raises(AsanaTaskPublishError, match="HTTP 401") as exc:
        publisher.publish(_tact_spec(), dry_run=False)

    assert exc.value.status_code == 401


def test_live_publish_raises_on_network_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("network unavailable", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = AsanaTaskPublisher("workspace-123", access_token="asana_pat", client=client)

    with pytest.raises(AsanaTaskPublishError, match="network unavailable"):
        publisher.publish(_tact_spec(), dry_run=False)


def test_from_env_reads_workspace_and_access_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASANA_WORKSPACE_GID", "workspace-env")
    monkeypatch.setenv("ASANA_ACCESS_TOKEN", "asana_env")

    publisher = AsanaTaskPublisher.from_env()

    assert publisher.workspace_gid == "workspace-env"
    assert publisher.access_token == "asana_env"


def test_section_requires_project() -> None:
    with pytest.raises(AsanaTaskPublishError, match="project_gid is required"):
        AsanaTaskPublisher("workspace-123", section_gid="section-123")


def _json_from_request(request: httpx.Request) -> dict:
    return json.loads(request.read())
