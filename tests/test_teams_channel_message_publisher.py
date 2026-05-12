from __future__ import annotations

import json

import httpx
import pytest

from max.publisher.teams_channel_messages import TeamsChannelMessagePublishError, TeamsChannelMessagePublisher
from tests.test_zoom_chat_webhook_publisher import _idea_payload


def test_dry_run_returns_exact_graph_payload_without_network() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not call Graph")

    publisher = TeamsChannelMessagePublisher(team_id="team-1", channel_id="channel-1", subject="Max update", importance="high", client=httpx.Client(transport=httpx.MockTransport(handler)))

    result = publisher.publish(_idea_payload(), dry_run=True)

    assert result.status_code is None
    assert result.payload["graph_payload"] == {
        "body": {"contentType": "html", "content": "<h2>Zoom Chat Publisher</h2><p>Publish Max ideas into Zoom Team Chat.</p>"},
        "subject": "Max update",
        "importance": "high",
    }
    assert result.payload["metadata"]["idea_id"] == "bu-zoom001"


def test_text_body_override_builds_payload() -> None:
    publisher = TeamsChannelMessagePublisher(team_id="team", channel_id="channel", content_type="text")

    payload = publisher.build_message_payload("plain message", subject="Subject").to_dict()

    assert payload["graph_payload"]["subject"] == "Subject"
    assert payload["graph_payload"]["body"] == {"contentType": "text", "content": "plain message"}


def test_live_publish_posts_graph_chat_message() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json={"id": "msg-1", "webUrl": "https://teams.microsoft.com/message/msg-1"})

    publisher = TeamsChannelMessagePublisher(access_token="token", team_id="team-1", channel_id="channel-1", api_url="https://graph.example/v1.0", client=httpx.Client(transport=httpx.MockTransport(handler)))

    result = publisher.publish(_idea_payload(), dry_run=False)

    assert result.status_code == 201
    assert result.message_id == "msg-1"
    assert requests[0].url == "https://graph.example/v1.0/teams/team-1/channels/channel-1/messages"
    assert requests[0].headers["Authorization"] == "Bearer token"
    assert json.loads(requests[0].read())["body"]["contentType"] == "html"


def test_validation_auth_and_error_responses() -> None:
    publisher = TeamsChannelMessagePublisher()
    with pytest.raises(TeamsChannelMessagePublishError, match="team_id"):
        publisher.publish("hello", dry_run=True)

    publisher = TeamsChannelMessagePublisher(team_id="team", channel_id="channel")
    with pytest.raises(TeamsChannelMessagePublishError, match="access_token"):
        publisher.publish("hello", dry_run=False)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="denied")

    publisher = TeamsChannelMessagePublisher(access_token="token", team_id="team", channel_id="channel", client=httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(TeamsChannelMessagePublishError) as exc:
        publisher.publish("hello", dry_run=False)
    assert exc.value.status_code == 403
