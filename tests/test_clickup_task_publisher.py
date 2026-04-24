"""Tests for ClickUp task publishing."""

from __future__ import annotations

import json

import httpx
import pytest

from max.publisher.clickup_tasks import ClickUpTaskPublishError, ClickUpTaskPublisher


def _tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {
            "system": "max",
            "type": "idea",
            "idea_id": "bu-clickup001",
            "status": "approved",
            "domain": "devtools",
            "category": "automation",
            "created_at": "2026-04-22T00:00:00+00:00",
            "updated_at": "2026-04-22T00:00:00+00:00",
        },
        "project": {
            "title": "ClickUp Publish Idea",
            "summary": "Publish implementation-ready ideas to ClickUp",
            "target_users": "developers",
        },
        "problem": {"statement": "Reviewed ideas are trapped in Max"},
        "solution": {"approach": "Create ClickUp tasks through REST"},
        "execution": {
            "mvp_scope": ["ClickUp publisher", "REST endpoint"],
            "validation_plan": "Publish one approved idea into a test list.",
        },
        "evidence": {
            "rationale": "Teams coordinate execution in ClickUp.",
            "insight_ids": ["ins-clickup001"],
            "signal_ids": ["sig-clickup001"],
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
    publisher = ClickUpTaskPublisher(
        "list-123",
        assignees=[101, 202],
        tags=["handoff"],
        priority=2,
        due_date=1777593600000,
        custom_fields=[{"id": "field-1", "value": "max"}],
    )

    payload = publisher.build_task_payload(_tact_spec()).to_dict()

    assert payload["name"] == "[Max] ClickUp Publish Idea"
    assert payload["list_id"] == "list-123"
    assert payload["assignees"] == [101, 202]
    assert payload["priority"] == 2
    assert payload["due_date"] == 1777593600000
    assert payload["custom_fields"] == [{"id": "field-1", "value": "max"}]
    assert "handoff" in payload["tags"]
    assert "Idea ID: bu-clickup001" in payload["description"]
    assert "Evidence Chain" in payload["description"]
    assert "Publish one approved idea" in payload["description"]


def test_dry_run_returns_exact_clickup_payload_without_token_or_network() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = ClickUpTaskPublisher("list-123", tags=["handoff"], client=client)

    result = publisher.publish(_tact_spec(), dry_run=True)

    assert result.dry_run is True
    assert result.status_code is None
    assert result.task_id is None
    assert result.task_url is None
    assert result.payload["name"] == "[Max] ClickUp Publish Idea"
    assert result.payload["list_id"] == "list-123"
    assert result.payload["tags"][-1] == "handoff"


def test_live_publish_posts_clickup_task_request_shape() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"id": "task-123", "url": "https://app.clickup.com/t/task-123"},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = ClickUpTaskPublisher(
        "list-123",
        api_token="clickup_pat",
        assignees=[101],
        tags=["handoff"],
        priority=1,
        due_date="1777593600000",
        custom_fields=[{"id": "field-1", "value": True}],
        client=client,
    )

    result = publisher.publish(_tact_spec(), dry_run=False)

    assert result.status_code == 200
    assert result.task_id == "task-123"
    assert result.task_url == "https://app.clickup.com/t/task-123"
    assert requests[0].url == "https://api.clickup.com/api/v2/list/list-123/task"
    assert requests[0].headers["Authorization"] == "clickup_pat"
    posted = _json_from_request(requests[0])
    assert posted["name"] == "[Max] ClickUp Publish Idea"
    assert posted["assignees"] == [101]
    assert posted["tags"][-1] == "handoff"
    assert posted["priority"] == 1
    assert posted["due_date"] == 1777593600000
    assert posted["custom_fields"] == [{"id": "field-1", "value": True}]
    assert "Create ClickUp tasks through REST" in posted["description"]


def test_live_publish_requires_api_token_before_network_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("missing token should fail before network calls")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = ClickUpTaskPublisher("list-123", client=client)

    with pytest.raises(ClickUpTaskPublishError, match="CLICKUP_API_TOKEN is required"):
        publisher.publish(_tact_spec(), dry_run=False)


def test_from_env_requires_list_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLICKUP_LIST_ID", raising=False)

    with pytest.raises(ClickUpTaskPublishError, match="list_id is required"):
        ClickUpTaskPublisher.from_env()


def test_live_publish_raises_structured_error_on_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"err": "List not found"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = ClickUpTaskPublisher("list-123", api_token="clickup_pat", client=client)

    with pytest.raises(ClickUpTaskPublishError, match="HTTP 400") as exc:
        publisher.publish(_tact_spec(), dry_run=False)

    assert exc.value.status_code == 400


def test_from_env_reads_fallbacks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLICKUP_LIST_ID", "list-env")
    monkeypatch.setenv("CLICKUP_API_TOKEN", "token-env")
    monkeypatch.setenv("CLICKUP_ASSIGNEES", "101,202")
    monkeypatch.setenv("CLICKUP_TAGS", "one,two")
    monkeypatch.setenv("CLICKUP_PRIORITY", "3")
    monkeypatch.setenv("CLICKUP_DUE_DATE", "1777593600000")
    monkeypatch.setenv("CLICKUP_CUSTOM_FIELDS", '[{"id":"field-1","value":"env"}]')

    publisher = ClickUpTaskPublisher.from_env()

    assert publisher.list_id == "list-env"
    assert publisher.api_token == "token-env"
    assert publisher.assignees == [101, 202]
    assert publisher.tags == ["one", "two"]
    assert publisher.priority == 3
    assert publisher.due_date == 1777593600000
    assert publisher.custom_fields == [{"id": "field-1", "value": "env"}]


def _json_from_request(request: httpx.Request) -> dict:
    return json.loads(request.read())
