from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx

from max.publisher.google_calendar_events import GoogleCalendarEventPublisher
from tests.test_intercom_conversation_note_publisher import _tact_spec


def test_dry_run_builds_google_calendar_event_payload() -> None:
    start = datetime(2026, 5, 12, 9, 0, tzinfo=timezone.utc)
    publisher = GoogleCalendarEventPublisher(calendar_id="team calendar", default_duration_minutes=45)

    result = publisher.publish(_tact_spec(), dry_run=True, start=start)

    event = result.payload["event"]
    assert result.dry_run is True
    assert event["summary"] == "Intercom Conversation Note Publisher"
    assert event["start"]["dateTime"] == "2026-05-12T09:00:00+00:00"
    assert event["end"]["dateTime"] == "2026-05-12T09:45:00+00:00"
    assert "Support teams need handoff context" in event["description"]


def test_live_publish_url_encodes_calendar_id() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"id": "evt_123", "htmlLink": "https://calendar/event"})

    publisher = GoogleCalendarEventPublisher(
        calendar_id="team calendar@example.com",
        access_token="google_token",
        api_url="https://google.example.test",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = publisher.publish(_tact_spec(), dry_run=False)

    assert result.event_id == "evt_123"
    assert requests[0].url == "https://google.example.test/calendar/v3/calendars/team%20calendar%40example.com/events"
    assert requests[0].headers["Authorization"] == "Bearer google_token"
    assert json.loads(requests[0].read())["summary"] == "Intercom Conversation Note Publisher"
