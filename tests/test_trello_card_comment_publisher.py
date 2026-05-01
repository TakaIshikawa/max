"""Tests for Trello card comment publishing."""

from __future__ import annotations

import json

import httpx
import pytest

from max.publisher import (
    TrelloCardCommentPublisher as ExportedTrelloCardCommentPublisher,
)
from max.publisher.trello_card_comments import (
    TrelloCardCommentPublishError,
    TrelloCardCommentPublisher,
)


def _tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {
            "system": "max",
            "type": "idea",
            "idea_id": "bu-trello-comment001",
            "status": "approved",
        },
        "project": {
            "title": "Trello Card Comment Publisher",
            "summary": "Append generated specs to existing Trello cards",
        },
    }


def test_comment_endpoint_uses_card_id() -> None:
    publisher = TrelloCardCommentPublisher(card_id="card-123")

    assert (
        publisher.comment_endpoint() == "https://api.trello.com/1/cards/card-123/actions/comments"
    )


def test_comment_endpoint_can_use_card_short_link() -> None:
    publisher = TrelloCardCommentPublisher(card_short_link="abc123")

    assert publisher.comment_endpoint() == "https://api.trello.com/1/cards/abc123/actions/comments"


def test_dry_run_returns_intended_request_without_network_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = TrelloCardCommentPublisher(
        card_short_link="abc123",
        key="trello_key",
        token="trello_token",
        client=client,
    )

    result = publisher.publish(
        _tact_spec(),
        markdown="## Generated Spec\n\nShip the comment publisher.",
        dry_run=True,
    )

    assert result.dry_run is True
    assert result.status_code is None
    assert result.card_id == "abc123"
    assert result.card_url == "https://trello.com/c/abc123"
    assert result.comment_id is None
    assert result.payload["text"] == "## Generated Spec\n\nShip the comment publisher."
    assert result.payload["metadata"]["publisher"] == "max.trello_card_comments"
    assert result.payload["request"] == {
        "method": "POST",
        "url": "https://api.trello.com/1/cards/abc123/actions/comments",
        "params": {"key": "trello_key", "token": "trello_token"},
        "json": {"text": "## Generated Spec\n\nShip the comment publisher."},
    }


def test_successful_publish_posts_comment_and_returns_id_card_and_url() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "id": "action-123",
                "data": {
                    "card": {
                        "id": "card-123",
                        "shortLink": "abc123",
                    }
                },
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = TrelloCardCommentPublisher(
        card_id="card-123",
        key="trello_key",
        token="trello_token",
        client=client,
    )

    result = publisher.publish(_tact_spec(), dry_run=False)

    assert result.status_code == 200
    assert result.card_id == "card-123"
    assert result.comment_id == "action-123"
    assert result.card_url == "https://trello.com/c/abc123"
    assert requests[0].url == (
        "https://api.trello.com/1/cards/card-123/actions/comments?key=trello_key&token=trello_token"
    )
    assert requests[0].headers["User-Agent"] == "max-trello-card-comments-publisher/1"
    posted = _json_from_request(requests[0])
    assert posted["text"].startswith("## Trello Card Comment Publisher")
    assert "Append generated specs" in posted["text"]
    assert result.payload["metadata"]["trello_card_comment_id"] == "action-123"
    assert result.payload["metadata"]["trello_card_url"] == "https://trello.com/c/abc123"


def test_missing_card_identifier_raises_publish_error() -> None:
    publisher = TrelloCardCommentPublisher()

    with pytest.raises(TrelloCardCommentPublishError, match="card_id or card_short_link"):
        publisher.publish(_tact_spec(), dry_run=True)


def test_live_publish_requires_credentials() -> None:
    publisher = TrelloCardCommentPublisher(card_id="card-123")

    with pytest.raises(TrelloCardCommentPublishError, match="TRELLO_KEY and TRELLO_TOKEN"):
        publisher.publish(_tact_spec(), dry_run=False)


def test_live_publish_raises_error_with_status_code_on_non_2xx() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(401, json={"message": "bad token=secret"})
        )
    )
    publisher = TrelloCardCommentPublisher(
        card_id="card-123",
        key="trello_key",
        token="trello_token",
        client=client,
    )

    with pytest.raises(TrelloCardCommentPublishError, match="HTTP 401") as exc:
        publisher.publish(_tact_spec(), dry_run=False)

    assert exc.value.status_code == 401
    assert "secret" not in str(exc.value)


def test_exported_from_publisher_package() -> None:
    assert ExportedTrelloCardCommentPublisher is TrelloCardCommentPublisher


def _json_from_request(request: httpx.Request) -> dict:
    return json.loads(request.read())
