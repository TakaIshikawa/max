"""Tests for the Hacker News Who Is Hiring source adapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from max.sources.base import _circuit_breakers
from max.sources.hackernews_whoishiring import (
    HackerNewsWhoIsHiringAdapter,
    _clean_hn_text,
    _parse_thread_month,
)
from max.types.signal import SignalSourceType


@pytest.fixture(autouse=True)
def _reset_circuit_breakers() -> None:
    _circuit_breakers.clear()


def _response(payload: dict | None) -> MagicMock:
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


def _thread(thread_id: int, *kids: int) -> dict:
    return {
        "id": thread_id,
        "type": "story",
        "title": "Ask HN: Who is hiring? (April 2026)",
        "kids": list(kids),
        "time": 1775000000,
    }


def _comment(
    comment_id: int,
    text: str,
    *,
    deleted: bool = False,
    dead: bool = False,
) -> dict:
    return {
        "id": comment_id,
        "type": "comment",
        "by": "founder",
        "time": 1775000100,
        "text": text,
        "deleted": deleted,
        "dead": dead,
    }


@pytest.mark.asyncio
async def test_fetch_discovers_thread_and_normalizes_hiring_comments() -> None:
    adapter = HackerNewsWhoIsHiringAdapter()
    requested_urls: list[str] = []

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        assert method == "GET"
        requested_urls.append(url)
        if url == "https://hn.algolia.com/api/v1/search":
            assert kwargs["params"]["query"] == "Ask HN: Who is hiring?"
            return _response(
                {
                    "hits": [
                        {
                            "objectID": "43000001",
                            "title": "Ask HN: Who is hiring? (April 2026)",
                        }
                    ]
                }
            )
        if url.endswith("/item/43000001.json"):
            return _response(_thread(43000001, 5001))
        if url.endswith("/item/5001.json"):
            return _response(
                _comment(
                    5001,
                    (
                        "Acme AI | NYC / Remote | Full-time<p>"
                        "Building developer tools with Python, TypeScript, Kubernetes, and LLMs."
                    ),
                )
            )
        raise AssertionError(f"unexpected URL: {url}")

    with patch("max.sources.hackernews_whoishiring.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=10)

    assert requested_urls[:2] == [
        "https://hn.algolia.com/api/v1/search",
        "https://hacker-news.firebaseio.com/v0/item/43000001.json",
    ]
    assert len(signals) == 1
    signal = signals[0]
    assert signal.id == "hackernews_whoishiring:5001"
    assert signal.source_adapter == "hackernews_whoishiring"
    assert signal.source_type == SignalSourceType.MARKET
    assert signal.title == "Acme AI hiring on Hacker News"
    assert signal.author == "founder"
    assert signal.url == "https://news.ycombinator.com/item?id=5001"
    assert signal.metadata["hn_comment_id"] == 5001
    assert signal.metadata["hn_thread_id"] == 43000001
    assert signal.metadata["company"] == "Acme AI"
    assert signal.metadata["location"] == "NYC / Remote"
    assert signal.metadata["remote"] is True
    assert signal.metadata["thread_month"] == "April 2026"
    assert signal.metadata["signal_role"] == "market"
    assert {"ai", "python", "typescript", "kubernetes"} <= set(
        signal.metadata["technologies"]
    )
    assert {"hiring", "market-demand", "remote"} <= set(signal.tags)


@pytest.mark.asyncio
async def test_fetch_uses_configured_item_ids_and_skips_discovery() -> None:
    adapter = HackerNewsWhoIsHiringAdapter(config={"item_ids": ["101"], "max_threads": 1})
    requested_urls: list[str] = []

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        requested_urls.append(url)
        if url.endswith("/item/101.json"):
            return _response(_thread(101, 201))
        if url.endswith("/item/201.json"):
            return _response(_comment(201, "DataCo | Berlin | ONSITE | Go and Rust"))
        raise AssertionError(f"unexpected URL: {url}")

    with patch("max.sources.hackernews_whoishiring.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=10)

    assert requested_urls == [
        "https://hacker-news.firebaseio.com/v0/item/101.json",
        "https://hacker-news.firebaseio.com/v0/item/201.json",
    ]
    assert len(signals) == 1
    assert signals[0].metadata["company"] == "DataCo"
    assert signals[0].metadata["remote"] is None
    assert {"go", "rust"} <= set(signals[0].metadata["technologies"])


@pytest.mark.asyncio
async def test_fetch_respects_limit_and_dedupes_by_comment_id() -> None:
    adapter = HackerNewsWhoIsHiringAdapter(config={"item_ids": [101, 102], "max_threads": 2})

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        if url.endswith("/item/101.json"):
            return _response(_thread(101, 201, 202))
        if url.endswith("/item/102.json"):
            return _response(_thread(102, 201, 203))
        if url.endswith("/item/201.json"):
            return _response(_comment(201, "OneCo | Remote | Python"))
        if url.endswith("/item/202.json"):
            return _response(_comment(202, "TwoCo | London | TypeScript"))
        if url.endswith("/item/203.json"):
            return _response(_comment(203, "ThreeCo | Berlin | Rust"))
        raise AssertionError(f"unexpected URL: {url}")

    with patch("max.sources.hackernews_whoishiring.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=2)

    assert [signal.metadata["hn_comment_id"] for signal in signals] == [201, 202]


@pytest.mark.asyncio
async def test_fetch_skips_deleted_dead_empty_and_nested_comments() -> None:
    adapter = HackerNewsWhoIsHiringAdapter(config={"item_ids": [101]})

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        if url.endswith("/item/101.json"):
            return _response(_thread(101, 201, 202, 203, 204, 205))
        if url.endswith("/item/201.json"):
            return _response(_comment(201, "DeletedCo | Remote | Python", deleted=True))
        if url.endswith("/item/202.json"):
            return _response(_comment(202, "DeadCo | Remote | Go", dead=True))
        if url.endswith("/item/203.json"):
            return _response(_comment(203, ""))
        if url.endswith("/item/204.json"):
            return _response({"id": 204, "type": "story", "title": "not a comment"})
        if url.endswith("/item/205.json"):
            return _response(_comment(205, "ValidCo | Remote | Security"))
        raise AssertionError(f"unexpected URL: {url}")

    with patch("max.sources.hackernews_whoishiring.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=10)

    assert [signal.metadata["company"] for signal in signals] == ["ValidCo"]


def test_parse_helpers() -> None:
    assert _parse_thread_month("Ask HN: Who is hiring? (February 2026)") == "February 2026"
    assert _parse_thread_month("Ask HN: Who is hiring?") is None
    assert _clean_hn_text("Acme &amp; Co<p>Python<br>TypeScript") == (
        "Acme & Co\nPython\nTypeScript"
    )
