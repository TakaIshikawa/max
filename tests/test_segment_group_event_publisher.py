from __future__ import annotations

import json

import httpx
import pytest

from max.publisher.segment_group_events import SegmentGroupEventPublishError, SegmentGroupEventPublisher
from tests.test_stripe_customer_note_publisher import _unit


def test_builds_segment_group_payload_fields() -> None:
    publisher = SegmentGroupEventPublisher(group_id="account_123", user_id="user_123")

    payload = publisher.build_group_payload(_unit()).to_dict()

    assert payload["group"]["groupId"] == "account_123"
    assert payload["group"]["userId"] == "user_123"
    assert payload["group"]["traits"]["max_idea_id"] == "bu-stripe001"
    assert payload["group"]["traits"]["max_title"] == "Stripe Customer Note Publisher"
    assert payload["group"]["traits"]["max_status"] == "approved"
    assert payload["group"]["context"]["integration"]["name"] == "max.segment_group_events"
    assert payload["metadata"]["publisher"] == "max.segment_group_events"


def test_from_env_reads_segment_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEGMENT_WRITE_KEY", "env-key")
    monkeypatch.setenv("SEGMENT_GROUP_ID", "env-group")
    monkeypatch.setenv("SEGMENT_USER_ID", "env-user")
    monkeypatch.setenv("SEGMENT_API_URL", "https://segment.example.test")

    publisher = SegmentGroupEventPublisher.from_env(max_retries=3)

    assert publisher.write_key == "env-key"
    assert publisher.group_id == "env-group"
    assert publisher.user_id == "env-user"
    assert publisher.api_url == "https://segment.example.test"
    assert publisher.max_retries == 3


def test_dry_run_returns_redacted_basic_auth_without_network() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    publisher = SegmentGroupEventPublisher(write_key="secret-key", group_id="account_123", client=httpx.Client(transport=httpx.MockTransport(handler)))

    result = publisher.publish(_unit(), dry_run=True)

    assert result.dry_run is True
    assert result.status_code is None
    assert result.authorization == "Basic [REDACTED]"
    assert result.endpoint == "https://api.segment.io/v1/group"
    assert result.payload["group"]["groupId"] == "account_123"


def test_live_publish_posts_group_request_and_parses_response() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"success": True})

    publisher = SegmentGroupEventPublisher(write_key="seg-key", group_id="account_123", user_id="user_123", api_url="https://segment.example.test", client=httpx.Client(transport=httpx.MockTransport(handler)))

    result = publisher.publish(_unit(), dry_run=False)

    assert result.status_code == 200
    assert result.response == {"success": True}
    assert requests[0].url == "https://segment.example.test/v1/group"
    assert requests[0].headers["Authorization"].startswith("Basic ")
    posted = json.loads(requests[0].read())
    assert posted["groupId"] == "account_123"
    assert posted["userId"] == "user_123"
    assert posted["traits"]["max_problem"] == "Billing teams need approved idea context."


def test_live_publish_requires_write_key() -> None:
    publisher = SegmentGroupEventPublisher(group_id="account_123")

    with pytest.raises(SegmentGroupEventPublishError, match="SEGMENT_WRITE_KEY"):
        publisher.publish(_unit(), dry_run=False)


def test_missing_group_id_is_actionable() -> None:
    publisher = SegmentGroupEventPublisher(write_key="seg-key")

    with pytest.raises(SegmentGroupEventPublishError, match="SEGMENT_GROUP_ID"):
        publisher.publish(_unit(), dry_run=True)


def test_retryable_failure_retries_and_redacts_secret() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, text="temporarily unavailable Basic secret-key")

    publisher = SegmentGroupEventPublisher(write_key="secret-key", group_id="account_123", max_retries=2, client=httpx.Client(transport=httpx.MockTransport(handler)))

    with pytest.raises(SegmentGroupEventPublishError, match="HTTP 503") as exc:
        publisher.publish(_unit(), dry_run=False)

    assert calls == 3
    assert exc.value.status_code == 503
    assert "secret-key" not in str(exc.value)
    assert "Basic [REDACTED]" in str(exc.value)
