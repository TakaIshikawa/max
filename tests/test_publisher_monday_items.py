from __future__ import annotations

import json

import httpx
import pytest

from max.publisher import MondayItemPublisher as ExportedMondayItemPublisher
from max.publisher.monday_items import MondayItemPublishError, MondayItemPublisher
from tests.test_intercom_conversation_note_publisher import _tact_spec


def test_monday_item_dry_run_payload_is_stable_and_deterministic() -> None:
    publisher = MondayItemPublisher(
        "12345",
        group_id="topics",
        item_name="Launch review",
        column_values={"priority": "High", "nested": {"b": 2, "a": 1}},
    )

    result = publisher.publish(_tact_spec(), dry_run=True)

    assert result.dry_run is True
    assert result.board_id == "12345"
    assert result.group_id == "topics"
    assert result.payload["variables"]["item_name"] == "Launch review"
    assert json.loads(result.payload["variables"]["column_values"])["nested"] == {"a": 1, "b": 2}
    assert result.payload["variables"]["column_values"] == json.dumps(json.loads(result.payload["variables"]["column_values"]), sort_keys=True)


def test_monday_item_validates_board_id_and_item_name() -> None:
    with pytest.raises(MondayItemPublishError, match="board_id"):
        MondayItemPublisher(" ")

    publisher = MondayItemPublisher("123", item_name=" ")
    assert publisher.publish({"project": {"title": "Fallback"}}, dry_run=True).payload["variables"]["item_name"] == "[Max] Fallback"


def test_monday_item_live_publish_posts_graphql_mutation() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"data": {"create_item": {"id": "987", "name": "Launch review", "url": "https://monday.test/items/987"}}})

    publisher = MondayItemPublisher(
        "12345",
        api_token="secret-token",
        api_url="https://monday.example.test/v2",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = publisher.publish(_tact_spec(), dry_run=False)

    assert result.item_id == "987"
    assert requests[0].url == "https://monday.example.test/v2"
    assert requests[0].headers["Authorization"] == "secret-token"
    posted = json.loads(requests[0].read())
    assert "mutation CreateMaxIdeaItem" in posted["query"]
    assert posted["variables"]["board_id"] == "12345"


def test_monday_item_graphql_errors_are_normalized_and_redacted() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"errors": [{"message": "bad token secret-token"}]})

    publisher = MondayItemPublisher(
        "12345",
        api_token="secret-token",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(MondayItemPublishError) as exc:
        publisher.publish(_tact_spec(), dry_run=False)

    assert "GraphQL errors" in str(exc.value)
    assert "secret-token" not in str(exc.value)
    assert "[redacted]" in str(exc.value)


def test_monday_item_publisher_is_exported() -> None:
    assert ExportedMondayItemPublisher is MondayItemPublisher
