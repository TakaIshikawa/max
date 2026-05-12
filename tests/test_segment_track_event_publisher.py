from __future__ import annotations

import json

import httpx
import pytest

from max.publisher.segment_track_events import (
    SegmentTrackEventPublishError,
    SegmentTrackEventPublisher,
)
from tests.test_intercom_conversation_note_publisher import _tact_spec


def test_dry_run_returns_segment_track_payload() -> None:
    publisher = SegmentTrackEventPublisher(user_id="user_123")

    result = publisher.publish(_tact_spec(), dry_run=True)

    event = result.payload["event"]
    assert result.dry_run is True
    assert event["event"] == "TactSpec Published"
    assert event["userId"] == "user_123"
    assert event["properties"]["source"]["idea_id"] == "bu-intercom001"
    assert event["properties"]["quality"]["quality_score"] == 8.0
    assert event["properties"]["evaluation"]["recommendation"] == "yes"


def test_requires_user_or_anonymous_id() -> None:
    publisher = SegmentTrackEventPublisher()

    with pytest.raises(SegmentTrackEventPublishError, match="SEGMENT_USER_ID or SEGMENT_ANONYMOUS_ID"):
        publisher.publish(_tact_spec(), dry_run=True)


def test_live_publish_posts_segment_track_event() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"success": True})

    publisher = SegmentTrackEventPublisher(
        write_key="seg_key",
        anonymous_id="anon_123",
        api_url="https://segment.example.test",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = publisher.publish(_tact_spec(), dry_run=False)

    assert result.status_code == 200
    assert requests[0].url == "https://segment.example.test/v1/track"
    assert requests[0].headers["Authorization"].startswith("Basic ")
    assert json.loads(requests[0].read())["anonymousId"] == "anon_123"
