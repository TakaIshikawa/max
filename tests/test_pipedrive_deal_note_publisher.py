from __future__ import annotations

import json

import httpx

from max.publisher.pipedrive_deal_notes import PipedriveDealNotePublisher
from tests.test_intercom_conversation_note_publisher import _tact_spec


def test_dry_run_returns_pipedrive_note_payload_without_network() -> None:
    publisher = PipedriveDealNotePublisher(deal_id="42")

    result = publisher.publish(_tact_spec(), dry_run=True)

    assert result.dry_run is True
    assert result.payload["deal_id"] == "42"
    assert "Intercom Conversation Note Publisher" in result.payload["content"]
    assert result.payload["metadata"]["publisher"] == "max.pipedrive_deal_notes"


def test_live_publish_posts_note_and_returns_note_id() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json={"data": {"id": 99}})

    publisher = PipedriveDealNotePublisher(
        deal_id="42",
        api_token="pd_token",
        api_url="https://pipedrive.example.test",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = publisher.publish(_tact_spec(), dry_run=False)

    assert result.note_id == "99"
    assert requests[0].url == "https://pipedrive.example.test/v1/notes?api_token=pd_token"
    posted = json.loads(requests[0].read())
    assert posted["deal_id"] == "42"
    assert "Intercom Conversation Note Publisher" in posted["content"]
