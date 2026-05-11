"""Tests for Eventbrite import adapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from max.imports.eventbrite_adapter import (
    EventbriteAdapter,
    _extract_format,
    _extract_pricing,
    _parse_dt,
)
from max.types.signal import SignalSourceType


MOCK_EVENTBRITE_PAGE_1 = {
    "events": [
        {
            "id": "1001",
            "name": {"text": "AI Platform Engineering Summit"},
            "description": {
                "text": "A conference about AI, APIs, Kubernetes, and developer tooling."
            },
            "url": "https://www.eventbrite.com/e/ai-platform-engineering-summit-1001",
            "start": {"utc": "2026-06-15T17:00:00Z"},
            "capacity": 450,
            "is_free": False,
            "online_event": False,
            "status": "live",
            "category": {"id": "102", "name": "Science & Technology"},
            "format": {"short_name": "Conference"},
            "venue": {"name": "Moscone Center", "address": {"city": "San Francisco"}},
            "organizer": {"id": "org-1", "name": "DevEvents"},
            "speakers": [{"name": "Maya Chen, Cloud API Architect"}],
            "ticket_classes": [
                {"name": "Early Bird", "cost": {"currency": "USD", "major_value": "199.00"}},
                {"name": "General", "cost": {"currency": "USD", "major_value": "299.00"}},
            ],
            "ticket_availability": {"has_available_tickets": True},
        }
    ],
    "pagination": {"has_more_items": True, "continuation": "next"},
}

MOCK_EVENTBRITE_PAGE_2 = {
    "events": [
        {
            "id": "1002",
            "name": {"text": "Security Automation Workshop"},
            "description": {"text": "Hands-on workshop for security automation teams."},
            "url": "https://www.eventbrite.com/e/security-automation-workshop-1002",
            "start": {"utc": "2026-07-01T16:00:00Z"},
            "listed_capacity": "75",
            "is_free": True,
            "online_event": True,
            "organizer": {"name": "SecureOps"},
            "presenters": ["Ravi Patel"],
        }
    ],
    "pagination": {"has_more_items": False},
}


def _mock_response(payload: dict) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.json.return_value = payload
    return resp


def test_parse_dt() -> None:
    parsed = _parse_dt("2026-06-15T17:00:00Z")
    assert parsed is not None
    assert parsed.year == 2026
    assert _parse_dt(None) is None


def test_extract_pricing_from_ticket_classes() -> None:
    pricing = _extract_pricing(MOCK_EVENTBRITE_PAGE_1["events"][0])
    assert pricing == {
        "is_free": False,
        "min_price": 199.0,
        "max_price": 299.0,
        "currency": "USD",
    }


def test_extract_format_online() -> None:
    assert _extract_format({"online_event": True}) == "online"


def test_adapter_properties_and_config() -> None:
    adapter = EventbriteAdapter(config={"categories": ["102"], "locations": ["Austin"]})
    assert adapter.name == "eventbrite_import"
    assert adapter.source_type == SignalSourceType.MARKET.value
    assert adapter.categories == ["102"]
    assert adapter.locations == ["Austin"]


@pytest.mark.asyncio
async def test_fetch_returns_empty_without_token() -> None:
    adapter = EventbriteAdapter()
    with patch("max.imports.eventbrite_adapter._get_token", return_value=None):
        assert await adapter.fetch(limit=10) == []


@pytest.mark.asyncio
async def test_fetch_parses_events_and_pagination() -> None:
    adapter = EventbriteAdapter(config={"categories": ["102"], "locations": ["San Francisco"]})

    with (
        patch("max.imports.eventbrite_adapter._get_token", return_value="token"),
        patch("max.imports.eventbrite_adapter.fetch_with_retry", new_callable=AsyncMock) as fetch,
    ):
        fetch.side_effect = [_mock_response(MOCK_EVENTBRITE_PAGE_1), _mock_response(MOCK_EVENTBRITE_PAGE_2)]
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 2
    assert fetch.await_count == 2
    first = signals[0]
    assert first.title == "AI Platform Engineering Summit"
    assert first.source_type == SignalSourceType.MARKET
    assert first.source_adapter == "eventbrite_import"
    assert first.author == "DevEvents"
    assert "ai" in first.tags
    assert "devtools" in first.tags
    assert first.metadata["capacity"] == 450
    assert first.metadata["pricing"]["min_price"] == 199.0
    assert first.metadata["format"] == "in_person"
    assert first.metadata["speakers"] == ["Maya Chen, Cloud API Architect"]
    assert first.metadata["ticket_sales"]["has_available_tickets"] is True
    assert signals[1].metadata["format"] == "online"
    assert signals[1].metadata["pricing"]["is_free"] is True


@pytest.mark.asyncio
async def test_fetch_respects_limit_and_deduplicates() -> None:
    dup_page = {"events": [MOCK_EVENTBRITE_PAGE_1["events"][0], MOCK_EVENTBRITE_PAGE_1["events"][0]], "pagination": {"has_more_items": False}}
    adapter = EventbriteAdapter(config={"categories": ["102"], "locations": ["San Francisco"]})

    with (
        patch("max.imports.eventbrite_adapter._get_token", return_value="token"),
        patch("max.imports.eventbrite_adapter.fetch_with_retry", new_callable=AsyncMock) as fetch,
    ):
        fetch.return_value = _mock_response(dup_page)
        signals = await adapter.fetch(limit=1)

    assert len(signals) == 1
    assert signals[0].metadata["event_id"] == "1001"


@pytest.mark.asyncio
async def test_fetch_handles_api_error() -> None:
    adapter = EventbriteAdapter(config={"categories": ["102"], "locations": ["San Francisco"]})
    with (
        patch("max.imports.eventbrite_adapter._get_token", return_value="token"),
        patch("max.imports.eventbrite_adapter.fetch_with_retry", new_callable=AsyncMock) as fetch,
    ):
        fetch.side_effect = Exception("boom")
        assert await adapter.fetch(limit=10) == []
