from __future__ import annotations

import json

import httpx
import pytest

from max.publisher.webex_space_messages import WebexSpaceMessagePublishError, WebexSpaceMessagePublisher
from tests.test_stripe_customer_note_publisher import _unit


def test_builds_webex_message_payload() -> None:
    publisher = WebexSpaceMessagePublisher(room_id="room_123")

    payload = publisher.build_message_payload(_unit())

    assert payload["roomId"] == "room_123"
    assert "Stripe Customer Note Publisher" in payload["markdown"]
    assert "**Idea ID:** bu-stripe001" in payload["markdown"]
    assert "**Status:** approved" in payload["markdown"]
    assert "**Score:** 87.0" in payload["markdown"]
    assert "Billing teams need approved idea context." in payload["markdown"]
    assert "Write deterministic customer metadata." in payload["markdown"]


def test_from_env_reads_webex_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEBEX_ACCESS_TOKEN", "env-token")
    monkeypatch.setenv("WEBEX_ROOM_ID", "env-room")
    monkeypatch.setenv("WEBEX_API_URL", "https://webex.example.test")

    publisher = WebexSpaceMessagePublisher.from_env(max_retries=3)

    assert publisher.access_token == "env-token"
    assert publisher.room_id == "env-room"
    assert publisher.api_url == "https://webex.example.test"
    assert publisher.max_retries == 3


def test_dry_run_avoids_network() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    publisher = WebexSpaceMessagePublisher(room_id="room_123", client=httpx.Client(transport=httpx.MockTransport(handler)))

    result = publisher.publish(_unit(), dry_run=True)

    assert result.dry_run is True
    assert result.endpoint == "https://webexapis.com/v1/messages"
    assert result.payload["roomId"] == "room_123"


def test_live_publish_posts_bearer_request_and_parses_message() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"id": "msg_123", "webUrl": "https://webex.example.test/m/msg_123"})

    publisher = WebexSpaceMessagePublisher(access_token="webex-token", room_id="room_123", api_url="https://webex.example.test", client=httpx.Client(transport=httpx.MockTransport(handler)))

    result = publisher.publish(_unit(), dry_run=False)

    assert result.message_id == "msg_123"
    assert result.web_url == "https://webex.example.test/m/msg_123"
    assert requests[0].url == "https://webex.example.test/v1/messages"
    assert requests[0].headers["Authorization"] == "Bearer webex-token"
    assert json.loads(requests[0].read())["roomId"] == "room_123"


def test_missing_auth_is_actionable() -> None:
    publisher = WebexSpaceMessagePublisher(room_id="room_123")

    with pytest.raises(WebexSpaceMessagePublishError, match="WEBEX_ACCESS_TOKEN"):
        publisher.publish(_unit(), dry_run=False)


def test_retryable_error_retries_and_redacts_token() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(429, text="bad Bearer webex-token")

    publisher = WebexSpaceMessagePublisher(access_token="webex-token", room_id="room_123", max_retries=1, client=httpx.Client(transport=httpx.MockTransport(handler)))

    with pytest.raises(WebexSpaceMessagePublishError, match="HTTP 429") as exc:
        publisher.publish(_unit(), dry_run=False)

    assert calls == 2
    assert "webex-token" not in str(exc.value)
    assert "Bearer [REDACTED]" in str(exc.value)
