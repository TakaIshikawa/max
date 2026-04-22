"""Tests for the Bluesky source adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from max.sources.bluesky import BLUESKY_SEARCH_URL, BlueskyAdapter
from max.types.signal import SignalSourceType


MOCK_POSTS = [
    {
        "uri": "at://did:plc:alice/app.bsky.feed.post/abc123",
        "cid": "bafyabc",
        "author": {
            "did": "did:plc:alice",
            "handle": "alice.dev",
            "displayName": "Alice Dev",
        },
        "record": {
            "text": "Shipping an MCP server for RAG workflows #MCP #AI",
            "createdAt": "2026-04-22T09:30:00Z",
            "tags": ["MCP", "AI"],
            "facets": [
                {
                    "features": [
                        {"tag": "DevTools"},
                        {"uri": "https://example.com/articles/mcp-rag"},
                    ]
                }
            ],
        },
        "replyCount": 3,
        "repostCount": 4,
        "likeCount": 20,
        "quoteCount": 2,
        "indexedAt": "2026-04-22T09:31:00Z",
        "embed": {"external": {"uri": "https://docs.example.org/mcp"}},
    },
    {
        "uri": "at://did:plc:bob/app.bsky.feed.post/def456",
        "cid": "bafydef",
        "author": {"did": "did:plc:bob", "handle": "bob.dev"},
        "record": {
            "text": "TypeScript agent tooling notes",
            "createdAt": "2026-04-22T10:00:00+00:00",
        },
        "replyCount": "1",
        "repostCount": "2",
        "likeCount": "5",
        "quoteCount": None,
    },
]


def test_bluesky_adapter_properties() -> None:
    adapter = BlueskyAdapter()

    assert adapter.name == "bluesky"
    assert adapter.source_type == SignalSourceType.FORUM.value
    assert "mcp" in adapter.queries


def test_bluesky_adapter_config_overrides_and_watchlist() -> None:
    adapter = BlueskyAdapter(
        config={
            "queries": ["mcp"],
            "watchlist_terms": ["rag"],
            "domains": ["developer-tools", "ai"],
        }
    )

    assert adapter.queries == ["mcp", "rag"]
    assert adapter.domains == ["developer-tools", "ai"]


@pytest.mark.asyncio
async def test_bluesky_fetch_parses_posts() -> None:
    adapter = BlueskyAdapter(config={"queries": ["mcp"]})

    with patch("max.sources.bluesky.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: {"posts": MOCK_POSTS})

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 2
    assert mock_fetch.call_args.args[0] == BLUESKY_SEARCH_URL
    assert mock_fetch.call_args.kwargs["params"] == {
        "q": "mcp",
        "sort": "latest",
        "limit": 10,
    }

    first = signals[0]
    assert first.source_type == SignalSourceType.FORUM
    assert first.source_adapter == "bluesky"
    assert first.title == "Shipping an MCP server for RAG workflows #MCP #AI"
    assert first.content == "Shipping an MCP server for RAG workflows #MCP #AI"
    assert first.url == "https://bsky.app/profile/alice.dev/post/abc123"
    assert first.author == "alice.dev"
    assert first.published_at == datetime(2026, 4, 22, 9, 30, tzinfo=timezone.utc)
    assert first.credibility == pytest.approx(0.43)
    assert first.metadata["uri"] == "at://did:plc:alice/app.bsky.feed.post/abc123"
    assert first.metadata["author_did"] == "did:plc:alice"
    assert first.metadata["search_query"] == "mcp"
    assert first.metadata["like_count"] == 20


@pytest.mark.asyncio
async def test_bluesky_fetch_returns_empty_results() -> None:
    adapter = BlueskyAdapter(config={"queries": ["nothing"]})

    with patch("max.sources.bluesky.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: {"posts": []})

        signals = await adapter.fetch(limit=10)

    assert signals == []


@pytest.mark.asyncio
async def test_bluesky_fetch_skips_malformed_posts() -> None:
    adapter = BlueskyAdapter(config={"queries": ["mcp"]})
    posts = [
        {"uri": "at://did:plc:bad/app.bsky.feed.post/no-record"},
        {"record": {"text": "missing uri"}},
        {"uri": "at://did:plc:bad/app.bsky.feed.post/no-text", "record": {}},
        MOCK_POSTS[1],
    ]

    with patch("max.sources.bluesky.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: {"posts": posts})

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].title == "TypeScript agent tooling notes"
    assert signals[0].metadata["like_count"] == 5
    assert signals[0].metadata["repost_count"] == 2


@pytest.mark.asyncio
async def test_bluesky_fetch_deduplicates_across_queries() -> None:
    adapter = BlueskyAdapter(config={"queries": ["mcp", "rag"]})

    with patch("max.sources.bluesky.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: {"posts": MOCK_POSTS})

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 2
    assert mock_fetch.call_count == 2


@pytest.mark.asyncio
async def test_bluesky_fetch_propagates_tags_and_domains() -> None:
    adapter = BlueskyAdapter(
        config={
            "queries": ["mcp server"],
            "domains": ["developer-tools", "ai"],
        }
    )

    with patch("max.sources.bluesky.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: {"posts": [MOCK_POSTS[0]]})

        signals = await adapter.fetch(limit=5)

    signal = signals[0]
    assert "bluesky" in signal.tags
    assert "mcp-server" in signal.tags
    assert "mcp" in signal.tags
    assert "ai" in signal.tags
    assert "developer-tools" in signal.tags
    assert signal.metadata["hashtags"] == ["mcp", "ai", "devtools"]
    assert signal.metadata["link_domains"] == ["example.com", "docs.example.org"]
    assert signal.metadata["configured_domains"] == ["developer-tools", "ai"]
