"""Tests for the Bluesky import adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from max.imports.bluesky_adapter import (
    BLUESKY_ACTOR_FEED_URL,
    BLUESKY_SEARCH_URL,
    BlueskyAdapter,
)
from max.types.signal import SignalSourceType


def _response(payload: object) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = payload
    return resp


def _post(
    post_id: str,
    *,
    text: str = "Shipping MCP tooling for agent workflows #MCP",
    handle: str = "alice.dev",
    created_at: str = "2026-04-22T09:30:00Z",
) -> dict:
    return {
        "uri": f"at://did:plc:alice/app.bsky.feed.post/{post_id}",
        "cid": f"bafy{post_id}",
        "author": {
            "did": "did:plc:alice",
            "handle": handle,
            "displayName": "Alice Dev",
        },
        "record": {
            "text": text,
            "createdAt": created_at,
            "tags": ["MCP"],
            "facets": [{"features": [{"tag": "DevTools"}, {"uri": "https://example.com/post"}]}],
        },
        "replyCount": 3,
        "repostCount": 4,
        "likeCount": 20,
        "quoteCount": 2,
        "indexedAt": "2026-04-22T09:31:00Z",
        "embed": {"external": {"uri": "https://docs.example.org/mcp"}},
    }


def test_bluesky_adapter_properties_and_config() -> None:
    adapter = BlueskyAdapter(
        config={
            "queries": ["mcp", "mcp"],
            "watchlist_terms": ["rag"],
            "handles": ["alice.dev"],
        }
    )

    assert adapter.name == "bluesky_import"
    assert adapter.source_type == SignalSourceType.FORUM.value
    assert adapter.queries == ["mcp", "rag"]
    assert adapter.handles == ["alice.dev"]


@pytest.mark.asyncio
async def test_fetch_search_posts_maps_core_fields() -> None:
    adapter = BlueskyAdapter(config={"queries": ["mcp"], "handles": []})

    with patch("max.imports.bluesky_adapter.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = _response({"posts": [_post("abc123")]})

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert mock_fetch.call_args.args[0] == BLUESKY_SEARCH_URL
    assert mock_fetch.call_args.kwargs["adapter_name"] == "bluesky_import"
    assert mock_fetch.call_args.kwargs["params"] == {"q": "mcp", "sort": "latest", "limit": 10}

    signal = signals[0]
    assert signal.source_adapter == "bluesky_import"
    assert signal.source_type == SignalSourceType.FORUM
    assert signal.title == "Shipping MCP tooling for agent workflows #MCP"
    assert signal.content == "Shipping MCP tooling for agent workflows #MCP"
    assert signal.author == "alice.dev"
    assert signal.url == "https://bsky.app/profile/alice.dev/post/abc123"
    assert signal.published_at == datetime(2026, 4, 22, 9, 30, tzinfo=timezone.utc)
    assert {"bluesky", "social", "mcp", "devtools"}.issubset(signal.tags)
    assert signal.credibility == pytest.approx(0.43)
    assert signal.metadata["like_count"] == 20
    assert signal.metadata["repost_count"] == 4
    assert signal.metadata["reply_count"] == 3
    assert signal.metadata["quote_count"] == 2
    assert signal.metadata["search_query"] == "mcp"
    assert signal.metadata["author_handle"] == "alice.dev"
    assert signal.metadata["link_domains"] == ["example.com", "docs.example.org"]


@pytest.mark.asyncio
async def test_fetch_actor_feed_unwraps_feed_items() -> None:
    adapter = BlueskyAdapter(config={"queries": [], "handles": ["alice.dev"]})

    with patch("max.imports.bluesky_adapter.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = _response({"feed": [{"post": _post("feed1", text="Actor feed post")} ]})

        signals = await adapter.fetch(limit=5)

    assert len(signals) == 1
    assert mock_fetch.call_args.args[0] == BLUESKY_ACTOR_FEED_URL
    assert mock_fetch.call_args.kwargs["params"] == {"actor": "alice.dev", "limit": 5}
    assert signals[0].title == "Actor feed post"
    assert signals[0].metadata["actor"] == "alice.dev"
    assert signals[0].metadata["search_query"] is None


@pytest.mark.asyncio
async def test_fetch_respects_limit_and_deduplicates_across_sources() -> None:
    adapter = BlueskyAdapter(config={"queries": ["mcp"], "handles": ["alice.dev"]})
    posts = [_post("one"), _post("two"), _post("one")]

    with patch("max.imports.bluesky_adapter.fetch_with_retry") as mock_fetch:
        mock_fetch.side_effect = [
            _response({"posts": posts}),
            _response({"feed": [{"post": _post("three")}]}),
        ]

        signals = await adapter.fetch(limit=2)

    assert [signal.url.rsplit("/", 1)[-1] for signal in signals] == ["one", "two"]
    assert mock_fetch.call_count == 1


@pytest.mark.asyncio
async def test_fetch_returns_partial_results_after_later_failure() -> None:
    adapter = BlueskyAdapter(config={"queries": ["mcp", "rag"], "handles": []})

    with patch("max.imports.bluesky_adapter.fetch_with_retry") as mock_fetch:
        mock_fetch.side_effect = [
            _response({"posts": [_post("ok")]}),
            RuntimeError("network failed"),
        ]

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].url.endswith("/ok")


@pytest.mark.asyncio
async def test_fetch_handles_empty_and_malformed_responses() -> None:
    adapter = BlueskyAdapter(config={"queries": ["mcp", "rag", "ai"], "handles": []})
    malformed = [
        {"uri": "at://did:plc:bad/app.bsky.feed.post/no-record"},
        {"record": {"text": "missing uri"}},
        {"uri": "at://did:plc:bad/app.bsky.feed.post/no-text", "record": {}},
        "not a post",
        _post("valid", text="Valid post"),
    ]

    with patch("max.imports.bluesky_adapter.fetch_with_retry") as mock_fetch:
        mock_fetch.side_effect = [
            _response({"posts": []}),
            _response({"posts": malformed}),
            _response(["not an object"]),
        ]

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].title == "Valid post"


@pytest.mark.asyncio
async def test_fetch_returns_empty_for_parse_failure_or_zero_limit() -> None:
    adapter = BlueskyAdapter(config={"queries": ["mcp"]})

    with patch("max.imports.bluesky_adapter.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=MagicMock(side_effect=ValueError("bad json")))

        assert await adapter.fetch(limit=10) == []

    assert await adapter.fetch(limit=0) == []
