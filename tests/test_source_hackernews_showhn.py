"""Tests for the Hacker News Show HN source adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from max.sources.base import AdapterFetchError, _circuit_breakers
from max.sources.errors import SourceParseError
from max.sources.hackernews_showhn import HackerNewsShowHNAdapter
from max.types.signal import SignalSourceType


@pytest.fixture(autouse=True)
def _reset_circuit_breakers() -> None:
    _circuit_breakers.clear()


def _response(payload: dict | list | None) -> MagicMock:
    response = MagicMock()
    response.status_code = 200
    response.json = MagicMock(return_value=payload)
    return response


def _mock_client(request):
    mock_client = AsyncMock()
    mock_client.request = AsyncMock(side_effect=request)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    return mock_client


def _hit(
    hn_id: int | str,
    title: str,
    *,
    url: str | None = "https://example.com/product",
    points: int = 123,
    comments: int = 45,
) -> dict:
    return {
        "objectID": str(hn_id),
        "title": title,
        "url": url,
        "author": "launchfounder",
        "points": points,
        "num_comments": comments,
        "created_at_i": 1712188800,
    }


@pytest.mark.asyncio
async def test_fetch_parses_show_hn_hits() -> None:
    adapter = HackerNewsShowHNAdapter()
    requested: list[tuple[str, dict]] = []

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        assert method == "GET"
        requested.append((url, kwargs["params"]))
        return _response(
            {
                "hits": [
                    _hit(
                        41001,
                        "Show HN: Prototype API monitor for developer teams",
                        points=250,
                        comments=67,
                    )
                ]
            }
        )

    with patch("max.sources.hackernews_showhn.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=5)

    assert requested == [
        (
            "https://hn.algolia.com/api/v1/search_by_date",
            {
                "query": "Show HN:",
                "tags": "story",
                "restrictSearchableAttributes": "title",
                "hitsPerPage": 5,
            },
        )
    ]
    assert len(signals) == 1
    signal = signals[0]
    assert signal.id == "hackernews_showhn:41001"
    assert signal.source_adapter == "hackernews_showhn"
    assert signal.source_type == SignalSourceType.FORUM
    assert signal.title == "Show HN: Prototype API monitor for developer teams"
    assert signal.content == signal.title
    assert signal.url == "https://example.com/product"
    assert signal.author == "launchfounder"
    assert signal.published_at == datetime(2024, 4, 4, tzinfo=timezone.utc)
    assert signal.credibility == 0.5
    assert signal.metadata["hn_id"] == 41001
    assert signal.metadata["score"] == 250
    assert signal.metadata["comments"] == 67
    assert signal.metadata["source_url"] == "https://news.ycombinator.com/item?id=41001"
    assert signal.metadata["signal_role"] == "market"
    assert {"show_hn", "product_launch", "prototype", "devtools"} <= set(signal.tags)


@pytest.mark.asyncio
async def test_fetch_empty_response_returns_no_signals() -> None:
    adapter = HackerNewsShowHNAdapter()

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        return _response({"hits": []})

    with patch("max.sources.hackernews_showhn.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=10)

    assert signals == []


@pytest.mark.asyncio
async def test_fetch_skips_malformed_and_non_show_hn_items() -> None:
    adapter = HackerNewsShowHNAdapter()

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        return _response(
            {
                "hits": [
                    None,
                    {"objectID": "missing-title"},
                    _hit("not-an-int", "Show HN: Missing valid ID"),
                    _hit(41002, "Ask HN: What should I build?"),
                    _hit(41003, "Show HN: AI launch tracker", url=None, points="bad"),
                ]
            }
        )

    with patch("max.sources.hackernews_showhn.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    signal = signals[0]
    assert signal.metadata["hn_id"] == 41003
    assert signal.url == "https://news.ycombinator.com/item?id=41003"
    assert signal.metadata["score"] == 0
    assert "ai" in signal.tags


@pytest.mark.asyncio
async def test_fetch_raises_parse_error_for_invalid_json() -> None:
    adapter = HackerNewsShowHNAdapter()
    response = MagicMock()
    response.status_code = 200
    response.json = MagicMock(side_effect=ValueError("bad json"))

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        return response

    with patch("max.sources.hackernews_showhn.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        with pytest.raises(SourceParseError, match="failed to parse Algolia response"):
            await adapter.fetch(limit=10)


@pytest.mark.asyncio
async def test_fetch_propagates_http_failure() -> None:
    adapter = HackerNewsShowHNAdapter()

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        response = MagicMock()
        response.status_code = 404
        response.json = MagicMock(return_value={"message": "not found"})
        return response

    with patch("max.sources.hackernews_showhn.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        with pytest.raises(AdapterFetchError) as exc_info:
            await adapter.fetch(limit=10)

    assert exc_info.value.adapter_name == "hackernews_showhn"
    assert exc_info.value.status_code == 404
