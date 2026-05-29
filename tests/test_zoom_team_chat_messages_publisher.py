from __future__ import annotations

import json

import httpx
import pytest

from max.publisher.zoom_team_chat_messages import ZoomTeamChatMessagePublishError, ZoomTeamChatMessagePublisher


def _spec() -> dict:
    return {"schema_version": "1", "kind": "tact", "project": {"title": "Zoom Chat Publisher", "summary": "Publish Max ideas into Zoom Team Chat."}, "source": {"idea_id": "bu-zoom001", "type": "idea"}}


def test_dry_run_returns_payload_without_network() -> None:
    publisher = ZoomTeamChatMessagePublisher(recipient_id="jid", client=httpx.Client(transport=httpx.MockTransport(lambda request: (_ for _ in ()).throw(AssertionError()))))
    result = publisher.publish(_spec(), dry_run=True)
    assert result.payload["endpoint"].endswith("/chat/users/me/messages")
    assert result.payload["recipient_id"] == "jid"
    assert result.payload["message"]["content"]["body"][0]["text"].startswith("# Zoom Chat Publisher")


def test_live_publish_posts_with_bearer_auth() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json={"id": "msg-1"})

    publisher = ZoomTeamChatMessagePublisher(access_token="secret", recipient_id="jid", api_url="https://zoom.example/v2", client=httpx.Client(transport=httpx.MockTransport(handler)))
    result = publisher.publish(_spec(), dry_run=False)
    assert result.message_id == "msg-1"
    assert requests[0].headers["Authorization"] == "Bearer secret"
    assert json.loads(requests[0].read())["to_jid"] == "jid"


def test_missing_token_and_http_failures_are_redacted() -> None:
    publisher = ZoomTeamChatMessagePublisher(recipient_id="jid")
    with pytest.raises(ZoomTeamChatMessagePublishError, match="ZOOM_ACCESS_TOKEN"):
        publisher.publish(_spec(), dry_run=False)
    publisher = ZoomTeamChatMessagePublisher(access_token="secret", recipient_id="jid", client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(500, text="bad secret"))))
    with pytest.raises(ZoomTeamChatMessagePublishError) as exc:
        publisher.publish(_spec(), dry_run=False)
    assert "secret" not in str(exc.value)
