from __future__ import annotations

import json

import httpx

from max.publisher.miro_board_cards import MiroBoardCardPublisher
from tests.test_intercom_conversation_note_publisher import _tact_spec


def test_dry_run_returns_miro_card_payload() -> None:
    publisher = MiroBoardCardPublisher(board_id="board 123")

    result = publisher.publish(_tact_spec(), dry_run=True)

    assert result.dry_run is True
    assert result.payload["board_id"] == "board 123"
    assert result.payload["card"]["data"]["title"] == "Intercom Conversation Note Publisher"
    assert "Support teams need handoff context" in result.payload["card"]["data"]["description"]


def test_live_publish_posts_card_and_returns_identifiers() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json={"id": "card_123", "viewLink": "https://miro/card"})

    publisher = MiroBoardCardPublisher(
        board_id="board 123",
        access_token="miro_token",
        api_url="https://miro.example.test",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = publisher.publish(_tact_spec(), dry_run=False)

    assert result.card_id == "card_123"
    assert result.card_link == "https://miro/card"
    assert requests[0].url == "https://miro.example.test/v2/boards/board%20123/cards"
    assert requests[0].headers["Authorization"] == "Bearer miro_token"
    assert json.loads(requests[0].read())["data"]["title"] == "Intercom Conversation Note Publisher"
