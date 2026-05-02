"""Tests for the WordPress.org plugin directory source adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from max.sources.base import _circuit_breakers
from max.sources.wordpress_plugins import DEFAULT_QUERIES, WordPressPluginsAdapter
from max.types.signal import SignalSourceType


@pytest.fixture(autouse=True)
def _reset_circuit_breakers() -> None:
    _circuit_breakers.clear()


def _response(payload: object, *, status_code: int = 200) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = payload
    return response


def _mock_client(request):
    mock_client = AsyncMock()
    mock_client.request = AsyncMock(side_effect=request)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    return mock_client


@pytest.mark.asyncio
async def test_fetch_configured_queries_as_registry_signals() -> None:
    adapter = WordPressPluginsAdapter(config={"queries": ["booking", "security"]})
    calls: list[dict] = []

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        calls.append(kwargs["params"])
        if kwargs["params"]["request[search]"] == "booking":
            return _response(
                {
                    "plugins": [
                        {
                            "name": "Booking Calendar",
                            "slug": "booking-calendar",
                            "rating": 96,
                            "active_installs": "600000",
                            "downloaded": 25_000_000,
                            "short_description": "Appointment booking for SMB websites.",
                            "author": '<a href="https://example.com">WP Booking</a>',
                            "tags": {
                                "booking": "Booking",
                                "calendar": "Calendar",
                                "appointments": "Appointments",
                            },
                            "last_updated": "2026-04-20 10:29am GMT",
                        }
                    ]
                }
            )
        if kwargs["params"]["request[search]"] == "security":
            return _response(
                {
                    "plugins": [
                        {
                            "name": "Security Scanner",
                            "slug": "security-scanner",
                            "rating": "88",
                            "active_installs": 100_000,
                            "short_description": "Finds vulnerable WordPress settings.",
                            "author": "Security Team",
                            "tags": ["security", "scanner"],
                            "last_updated": "2026-04-22T08:00:00Z",
                        }
                    ]
                }
            )
        raise AssertionError(f"unexpected query: {kwargs['params']}")

    with patch("max.sources.wordpress_plugins.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=10)

    assert [signal.metadata["wordpress_slug"] for signal in signals] == [
        "booking-calendar",
        "security-scanner",
    ]
    assert all(signal.source_adapter == "wordpress_plugins" for signal in signals)
    assert all(signal.source_type == SignalSourceType.REGISTRY for signal in signals)

    first = signals[0]
    assert first.id == "wordpress_plugins:booking-calendar"
    assert first.title == "Booking Calendar"
    assert first.content == "Appointment booking for SMB websites."
    assert first.url == "https://wordpress.org/plugins/booking-calendar/"
    assert first.author == "WP Booking"
    assert first.published_at == datetime(2026, 4, 20, 10, 29, tzinfo=timezone.utc)
    assert first.metadata["signal_role"] == "market"
    assert first.metadata["package_ecosystem"] == "wordpress"
    assert first.metadata["plugin_name"] == "Booking Calendar"
    assert first.metadata["search_query"] == "booking"
    assert first.metadata["rating"] == 96
    assert first.metadata["active_installs"] == 600_000
    assert first.metadata["downloaded"] == 25_000_000
    assert first.metadata["short_description"] == "Appointment booking for SMB websites."
    assert first.metadata["author"] == "WP Booking"
    assert first.metadata["tags"] == ["booking", "calendar", "appointments"]
    assert first.metadata["source_url"] == "https://wordpress.org/plugins/booking-calendar/"
    assert first.metadata["plugin_url"] == "https://wordpress.org/plugins/booking-calendar/"
    assert {
        "wordpress",
        "wordpress-plugin",
        "plugin-directory",
        "booking-calendar",
        "booking",
    } <= set(first.tags)
    assert calls[0]["action"] == "query_plugins"
    assert calls[0]["request[per_page]"] == 10


@pytest.mark.asyncio
async def test_defaults_custom_api_url_dedupe_and_limit_are_used() -> None:
    adapter = WordPressPluginsAdapter(
        config={"api_url": "https://wordpress.example/plugins", "max_items": 999}
    )
    urls: list[str] = []

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        urls.append(url)
        return _response(
            {
                "plugins": [
                    {
                        "name": "Duplicate One",
                        "slug": "duplicate-plugin",
                        "short_description": "First result wins.",
                    },
                    {
                        "name": "Duplicate Two",
                        "slug": "duplicate-plugin",
                        "short_description": "Should be skipped.",
                    },
                    {
                        "name": "Ignored",
                        "slug": "ignored",
                        "short_description": "Limit should stop before this.",
                    },
                ]
            }
        )

    with patch("max.sources.wordpress_plugins.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=1)

    assert adapter.queries == DEFAULT_QUERIES
    assert urls == ["https://wordpress.example/plugins"]
    assert len(signals) == 1
    assert signals[0].metadata["wordpress_slug"] == "duplicate-plugin"
    assert signals[0].title == "Duplicate One"


@pytest.mark.asyncio
async def test_malformed_responses_and_plugin_records_are_skipped() -> None:
    adapter = WordPressPluginsAdapter(config={"queries": ["bad-response", "mixed"]})

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        if kwargs["params"]["request[search]"] == "bad-response":
            return _response({"plugins": "not-a-list"})
        if kwargs["params"]["request[search]"] == "mixed":
            return _response(
                {
                    "plugins": [
                        "not-a-plugin",
                        {"name": "Missing slug", "short_description": "No slug."},
                        {
                            "name": "<strong>Valid</strong> Plugin",
                            "slug": "Valid Plugin!",
                            "short_description": "Useful &amp; clean.",
                            "rating": "nope",
                            "active_installs": "also nope",
                        },
                    ]
                }
            )
        raise AssertionError(f"unexpected query: {kwargs['params']}")

    with patch("max.sources.wordpress_plugins.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].id == "wordpress_plugins:valid-plugin"
    assert signals[0].title == "Valid Plugin"
    assert signals[0].content == "Useful & clean."
    assert signals[0].metadata["rating"] is None
    assert signals[0].metadata["active_installs"] is None


@pytest.mark.asyncio
async def test_api_error_does_not_fail_whole_fetch() -> None:
    adapter = WordPressPluginsAdapter(config={"queries": ["unavailable", "available"]})

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        if kwargs["params"]["request[search]"] == "unavailable":
            return _response({}, status_code=503)
        if kwargs["params"]["request[search]"] == "available":
            return _response(
                {
                    "plugins": [
                        {
                            "name": "Available Plugin",
                            "slug": "available-plugin",
                            "short_description": "Still fetched after an error.",
                        }
                    ]
                }
            )
        raise AssertionError(f"unexpected query: {kwargs['params']}")

    with patch("max.sources.wordpress_plugins.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].metadata["wordpress_slug"] == "available-plugin"


@pytest.mark.asyncio
async def test_empty_results_return_empty_list() -> None:
    adapter = WordPressPluginsAdapter(config={"queries": ["nothing"]})

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        return _response({"plugins": []})

    with patch("max.sources.wordpress_plugins.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=10)

    assert signals == []
