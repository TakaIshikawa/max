from __future__ import annotations

import httpx

from max.publisher.trello_card_comments import TrelloCardCommentPublishError, TrelloCardCommentPublisher


def test_missing_required_values_raise_clear_errors() -> None:
    try:
        TrelloCardCommentPublisher(key="k", token="t").publish("hello")
    except TrelloCardCommentPublishError as exc:
        assert "card" in str(exc).lower()


def test_dry_run_exposes_url_and_redacted_payload() -> None:
    result = TrelloCardCommentPublisher(card_id="card", key="k", token="t").publish("hello")
    assert result.payload["request"]["url"].endswith("/cards/card/actions/comments")
    assert result.payload["request"]["json"]["text"] == "hello"


def test_successful_fake_response_returns_stable_result() -> None:
    publisher = TrelloCardCommentPublisher(card_id="card", key="k", token="t", client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"id": "comment"}))))
    result = publisher.publish("hello", dry_run=False)
    assert result.comment_id == "comment"
