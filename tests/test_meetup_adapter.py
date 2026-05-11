"""Tests for Meetup import adapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from max.imports.meetup_adapter import MeetupAdapter, _parse_dt
from max.types.signal import SignalSourceType


MOCK_MEETUP_RESPONSE = {
    "events": [
        {
            "id": "m1",
            "name": "AI Developer Tools Meetup",
            "description": "<p>Talks about LLM APIs and platform engineering.</p>",
            "link": "https://meetup.com/devtools/events/m1",
            "time": 1_780_000_000_000,
            "yes_rsvp_count": 120,
            "rsvp_limit": 150,
            "group": {"id": 10, "name": "DevTools SF", "urlname": "devtools-sf", "members": 2400},
            "venue": {"name": "Startup Hub"},
        }
    ]
}


def _mock_response(payload: dict | list) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.json.return_value = payload
    return resp


def test_parse_dt_milliseconds() -> None:
    parsed = _parse_dt(1_780_000_000_000)
    assert parsed is not None
    assert parsed.year == 2026


def test_adapter_config() -> None:
    adapter = MeetupAdapter(config={"topics": ["cloud"], "locations": ["Austin"], "groups": ["atx-dev"]})
    assert adapter.name == "meetup_import"
    assert adapter.source_type == SignalSourceType.MARKET.value
    assert adapter.topics == ["cloud"]
    assert adapter.locations == ["Austin"]
    assert adapter.groups == ["atx-dev"]


@pytest.mark.asyncio
async def test_fetch_returns_empty_without_token() -> None:
    with patch("max.imports.meetup_adapter._get_token", return_value=None):
        assert await MeetupAdapter().fetch(limit=5) == []


@pytest.mark.asyncio
async def test_fetch_parses_topic_events() -> None:
    adapter = MeetupAdapter(config={"topics": ["developer-tools"], "locations": ["San Francisco"]})
    with (
        patch("max.imports.meetup_adapter._get_token", return_value="token"),
        patch("max.imports.meetup_adapter.fetch_with_retry", new_callable=AsyncMock) as fetch,
    ):
        fetch.return_value = _mock_response(MOCK_MEETUP_RESPONSE)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    signal = signals[0]
    assert signal.title == "AI Developer Tools Meetup"
    assert signal.source_type == SignalSourceType.MARKET
    assert "ai" in signal.tags
    assert "devtools" in signal.tags
    assert signal.metadata["rsvp_count"] == 120
    assert signal.metadata["capacity"] == 150
    assert signal.metadata["group"]["members"] == 2400
    assert signal.metadata["venue"] == "Startup Hub"


@pytest.mark.asyncio
async def test_fetch_group_events_and_deduplicates() -> None:
    adapter = MeetupAdapter(config={"groups": ["devtools-sf"], "topics": [], "locations": []})
    with (
        patch("max.imports.meetup_adapter._get_token", return_value="token"),
        patch("max.imports.meetup_adapter.fetch_with_retry", new_callable=AsyncMock) as fetch,
    ):
        fetch.return_value = _mock_response([MOCK_MEETUP_RESPONSE["events"][0], MOCK_MEETUP_RESPONSE["events"][0]])
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].metadata["event_id"] == "m1"


@pytest.mark.asyncio
async def test_fetch_handles_api_error() -> None:
    adapter = MeetupAdapter(config={"topics": ["cloud"], "locations": ["Austin"]})
    with (
        patch("max.imports.meetup_adapter._get_token", return_value="token"),
        patch("max.imports.meetup_adapter.fetch_with_retry", new_callable=AsyncMock) as fetch,
    ):
        fetch.side_effect = Exception("boom")
        assert await adapter.fetch(limit=5) == []
