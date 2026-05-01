"""Tests for the Hacker News Ask HN source adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from max.sources.base import AdapterFetchError, _circuit_breakers
from max.sources.errors import SourceParseError
from max.sources.hackernews_askhn import HackerNewsAskHNAdapter
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
    url: str | None = None,
    points: int | str = 88,
    comments: int | str = 19,
    author: str | None = "questioner",
) -> dict:
    return {
        "objectID": str(hn_id),
        "title": title,
        "url": url,
        "author": author,
        "points": points,
        "num_comments": comments,
        "story_text": "Manual workflow pain &amp; brittle API handoffs.",
        "created_at_i": 1712188800,
    }


@pytest.mark.asyncio
async def test_fetch_parses_ask_hn_hits() -> None:
    adapter = HackerNewsAskHNAdapter()
    requested: list[tuple[str, dict]] = []

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        assert method == "GET"
        requested.append((url, kwargs["params"]))
        return _response(
            {
                "hits": [
                    _hit(
                        42001,
                        "Ask HN: How do you handle manual API handoffs?",
                        url="https://example.com/context",
                        points=250,
                        comments=67,
                    )
                ]
            }
        )

    with patch("max.sources.hackernews_askhn.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=5)

    assert requested == [
        (
            "https://hn.algolia.com/api/v1/search_by_date",
            {
                "query": "Ask HN:",
                "tags": "story",
                "restrictSearchableAttributes": "title",
                "hitsPerPage": 5,
            },
        )
    ]
    assert len(signals) == 1
    signal = signals[0]
    assert signal.id == "hackernews_askhn:42001"
    assert signal.source_adapter == "hackernews_askhn"
    assert signal.source_type == SignalSourceType.FORUM
    assert signal.title == "Ask HN: How do you handle manual API handoffs?"
    assert signal.content == (
        "Ask HN: How do you handle manual API handoffs?\n\n"
        "Manual workflow pain & brittle API handoffs."
    )
    assert signal.url == "https://example.com/context"
    assert signal.author == "questioner"
    assert signal.published_at == datetime(2024, 4, 4, tzinfo=timezone.utc)
    assert signal.credibility == 0.5
    assert signal.metadata["hn_id"] == 42001
    assert signal.metadata["score"] == 250
    assert signal.metadata["comments"] == 67
    assert signal.metadata["comment_count"] == 67
    assert signal.metadata["author"] == "questioner"
    assert signal.metadata["url"] == "https://example.com/context"
    assert signal.metadata["source_url"] == "https://news.ycombinator.com/item?id=42001"
    assert signal.metadata["signal_role"] == "problem"
    assert signal.metadata["source_kind"] == "ask_hn"
    assert {"ask_hn", "problem_signal", "devtools", "workflow", "pain_point"} <= set(
        signal.tags
    )


@pytest.mark.asyncio
async def test_fetch_uses_configured_query_and_limit() -> None:
    adapter = HackerNewsAskHNAdapter(config={"query": "Ask HN: database"})
    requested_params: list[dict] = []

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        requested_params.append(kwargs["params"])
        return _response(
            {
                "hits": [
                    _hit(42001, "Ask HN: Database migration pain?"),
                    _hit(42002, "Ask HN: Database backups for small teams?"),
                ]
            }
        )

    with patch("max.sources.hackernews_askhn.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=1)

    assert requested_params == [
        {
            "query": "Ask HN: database",
            "tags": "story",
            "restrictSearchableAttributes": "title",
            "hitsPerPage": 1,
        }
    ]
    assert [signal.metadata["hn_id"] for signal in signals] == [42001]


@pytest.mark.asyncio
async def test_fetch_skips_malformed_and_non_ask_hn_items() -> None:
    adapter = HackerNewsAskHNAdapter()

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        return _response(
            {
                "hits": [
                    None,
                    {"objectID": "missing-title"},
                    _hit("not-an-int", "Ask HN: Missing valid ID"),
                    _hit(42002, "Show HN: AI launch tracker"),
                    _hit(42003, "Ask HN: Any CLI workflow pain?", points="bad", comments="bad"),
                ]
            }
        )

    with patch("max.sources.hackernews_askhn.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    signal = signals[0]
    assert signal.metadata["hn_id"] == 42003
    assert signal.url == "https://news.ycombinator.com/item?id=42003"
    assert signal.metadata["score"] == 0
    assert signal.metadata["comment_count"] == 0
    assert {"devtools", "workflow", "pain_point"} <= set(signal.tags)


@pytest.mark.asyncio
async def test_fetch_empty_or_malformed_hits_returns_no_signals() -> None:
    adapter = HackerNewsAskHNAdapter()

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        return _response({"hits": {"not": "a-list"}})

    with patch("max.sources.hackernews_askhn.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=10)

    assert signals == []


@pytest.mark.asyncio
async def test_fetch_raises_parse_error_for_invalid_json() -> None:
    adapter = HackerNewsAskHNAdapter()
    response = MagicMock()
    response.status_code = 200
    response.json = MagicMock(side_effect=ValueError("bad json"))

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        return response

    with patch("max.sources.hackernews_askhn.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        with pytest.raises(SourceParseError, match="failed to parse Algolia response"):
            await adapter.fetch(limit=10)


@pytest.mark.asyncio
async def test_fetch_propagates_http_failure() -> None:
    adapter = HackerNewsAskHNAdapter()

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        response = MagicMock()
        response.status_code = 404
        response.json = MagicMock(return_value={"message": "not found"})
        return response

    with patch("max.sources.hackernews_askhn.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        with pytest.raises(AdapterFetchError) as exc_info:
            await adapter.fetch(limit=10)

    assert exc_info.value.adapter_name == "hackernews_askhn"
    assert exc_info.value.status_code == 404
