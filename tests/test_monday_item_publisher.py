"""Tests for Monday.com item publishing."""

from __future__ import annotations

import json

import httpx
import pytest

from max.publisher.monday_items import MondayItemPublishError, MondayItemPublisher


def _tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {
            "system": "max",
            "type": "idea",
            "idea_id": "bu-monday001",
            "status": "approved",
            "domain": "devtools",
            "category": "automation",
            "created_at": "2026-04-22T00:00:00+00:00",
            "updated_at": "2026-04-22T00:00:00+00:00",
        },
        "project": {
            "title": "Monday Publish Idea",
            "summary": "Publish implementation-ready ideas to Monday.com",
            "target_users": "operators",
        },
        "problem": {"statement": "Reviewed ideas are trapped in Max"},
        "solution": {"approach": "Create Monday.com items through GraphQL"},
        "execution": {
            "mvp_scope": ["Monday publisher", "REST endpoint"],
            "validation_plan": "Publish one approved idea into a test board.",
        },
        "evidence": {
            "rationale": "Launch teams coordinate execution in Monday.com.",
            "insight_ids": ["ins-monday001"],
            "signal_ids": ["sig-monday001"],
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
        },
    }


def test_build_item_payload_maps_tact_spec_fields_to_graphql_variables() -> None:
    publisher = MondayItemPublisher(
        "board-123",
        group_id="topics",
        item_name="Custom Monday item",
        column_values={"owner": {"personsAndTeams": [{"id": 101, "kind": "person"}]}},
    )

    payload = publisher.build_item_payload(_tact_spec()).to_dict()

    assert "create_item" in payload["query"]
    assert payload["variables"]["board_id"] == "board-123"
    assert payload["variables"]["group_id"] == "topics"
    assert payload["variables"]["item_name"] == "Custom Monday item"
    columns = json.loads(payload["variables"]["column_values"])
    assert columns["problem"] == "Reviewed ideas are trapped in Max"
    assert columns["solution"] == "Create Monday.com items through GraphQL"
    assert columns["recommendation"] == "yes"
    assert columns["score"] == 82.0
    assert columns["validation_plan"] == "Publish one approved idea into a test board."
    assert columns["source_idea_id"] == "bu-monday001"
    assert columns["owner"] == {"personsAndTeams": [{"id": 101, "kind": "person"}]}
    assert payload["metadata"]["publisher"] == "max.monday_items"


def test_dry_run_returns_payload_without_token_or_network() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = MondayItemPublisher("board-123", group_id="topics", client=client)

    result = publisher.publish(_tact_spec(), dry_run=True)

    assert result.dry_run is True
    assert result.status_code is None
    assert result.item_id is None
    assert result.item_url is None
    assert result.payload["variables"]["item_name"] == "[Max] Monday Publish Idea"
    assert result.payload["variables"]["board_id"] == "board-123"


def test_live_publish_posts_monday_graphql_request_shape() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "data": {
                    "create_item": {
                        "id": "item-123",
                        "name": "Monday Publish Idea",
                        "url": "https://example.monday.com/boards/123/pulses/item-123",
                    }
                }
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = MondayItemPublisher(
        "board-123",
        api_token="monday_pat",
        group_id="topics",
        client=client,
    )

    result = publisher.publish(_tact_spec(), dry_run=False)

    assert result.status_code == 200
    assert result.item_id == "item-123"
    assert result.item_url == "https://example.monday.com/boards/123/pulses/item-123"
    assert requests[0].url == "https://api.monday.com/v2"
    assert requests[0].headers["Authorization"] == "monday_pat"
    posted = _json_from_request(requests[0])
    assert "create_item" in posted["query"]
    assert posted["variables"]["board_id"] == "board-123"
    assert posted["variables"]["group_id"] == "topics"
    assert posted["variables"]["item_name"] == "[Max] Monday Publish Idea"
    columns = json.loads(posted["variables"]["column_values"])
    assert columns["source_idea_id"] == "bu-monday001"


def test_live_publish_requires_api_token_before_network_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("missing token should fail before network calls")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = MondayItemPublisher("board-123", client=client)

    with pytest.raises(MondayItemPublishError, match="MONDAY_API_TOKEN is required"):
        publisher.publish(_tact_spec(), dry_run=False)


def test_from_env_reads_monday_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MONDAY_BOARD_ID", "board-env")
    monkeypatch.setenv("MONDAY_GROUP_ID", "group-env")
    monkeypatch.setenv("MONDAY_API_TOKEN", "token-env")

    publisher = MondayItemPublisher.from_env()

    assert publisher.board_id == "board-env"
    assert publisher.group_id == "group-env"
    assert publisher.api_token == "token-env"


def test_from_env_requires_board_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MONDAY_BOARD_ID", raising=False)

    with pytest.raises(MondayItemPublishError, match="board_id is required"):
        MondayItemPublisher.from_env()


def test_live_publish_redacts_token_from_http_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="bad token=monday_secret authorization=monday_secret")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = MondayItemPublisher("board-123", api_token="monday_secret", client=client)

    with pytest.raises(MondayItemPublishError, match="HTTP 401") as exc:
        publisher.publish(_tact_spec(), dry_run=False)

    assert exc.value.status_code == 401
    assert "monday_secret" not in str(exc.value)


def _json_from_request(request: httpx.Request) -> dict:
    return json.loads(request.read())
