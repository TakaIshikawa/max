from __future__ import annotations

import json

import httpx

from max.publisher import SlackMessagePublisher as ExportedSlackMessagePublisher
from max.publisher.slack_messages import SlackMessagePublisher
from tests.test_intercom_conversation_note_publisher import _tact_spec


def test_dry_run_returns_slack_message_payload() -> None:
    publisher = SlackMessagePublisher(channel="C123", thread_ts="123.456")

    result = publisher.publish(_tact_spec(), dry_run=True)

    assert result.dry_run is True
    assert result.channel == "C123"
    assert result.payload["message"]["thread_ts"] == "123.456"
    assert result.payload["message"]["mrkdwn"] is True
    assert "Intercom Conversation Note Publisher" in result.payload["message"]["text"]


def test_live_publish_posts_message_and_returns_channel_ts() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"ok": True, "channel": "C123", "ts": "789.012"})

    publisher = SlackMessagePublisher(
        bot_token="xoxb-token",
        channel="C123",
        api_url="https://slack.example.test/api",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = publisher.publish(_tact_spec(), dry_run=False, attachments=[{"color": "#2D9BF0"}])

    assert result.channel == "C123"
    assert result.ts == "789.012"
    assert requests[0].url == "https://slack.example.test/api/chat.postMessage"
    assert requests[0].headers["Authorization"] == "Bearer xoxb-token"
    posted = json.loads(requests[0].read())
    assert posted["attachments"] == [{"color": "#2D9BF0"}]


def test_slack_message_publisher_is_exported() -> None:
    assert ExportedSlackMessagePublisher is SlackMessagePublisher
