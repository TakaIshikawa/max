"""Tests for the Lobsters source adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from max.sources.lobsters import LobstersAdapter
from max.types.signal import SignalSourceType


MOCK_STORIES = [
    {
        "short_id": "abc123",
        "title": "Rust Async Debugging Tools",
        "url": "https://example.com/rust-async-debugging",
        "comments_url": "https://lobste.rs/s/abc123/rust_async_debugging_tools",
        "score": 42,
        "comment_count": 9,
        "submitter_user": "alice",
        "tags": ["rust", "debugging"],
        "created_at": "2026-04-21T10:30:00.000-05:00",
    },
    {
        "short_id": "def456",
        "title": "Practical Postgres Indexing",
        "url": "https://example.com/postgres-indexing",
        "short_id_url": "https://lobste.rs/s/def456",
        "score": 13,
        "comments_count": 4,
        "submitter": "bob",
        "tags": ["databases", "performance"],
        "created_at": "2026-04-22T09:00:00Z",
    },
]


@pytest.mark.asyncio
async def test_lobsters_fetch_parses_newest_stories() -> None:
    adapter = LobstersAdapter()

    with patch("max.sources.lobsters.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: MOCK_STORIES)

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 2
    assert mock_fetch.call_args.args[0] == "https://lobste.rs/newest.json"
    assert "params" not in mock_fetch.call_args.kwargs

    first = signals[0]
    assert first.source_type == SignalSourceType.FORUM
    assert first.source_adapter == "lobsters"
    assert first.title == "Rust Async Debugging Tools"
    assert first.content == "Rust Async Debugging Tools"
    assert first.url == "https://example.com/rust-async-debugging"
    assert first.author == "alice"
    assert first.published_at == datetime(2026, 4, 21, 10, 30, tzinfo=timezone.utc).replace(
        tzinfo=first.published_at.tzinfo
    )
    assert "rust" in first.tags
    assert "lobsters" in first.tags
    assert first.metadata["short_id"] == "abc123"
    assert first.metadata["comments_url"] == "https://lobste.rs/s/abc123/rust_async_debugging_tools"
    assert first.metadata["submitter"] == "alice"
    assert first.metadata["score"] == 42
    assert first.metadata["comment_count"] == 9


@pytest.mark.asyncio
async def test_lobsters_fetch_uses_tag_pages_and_deduplicates() -> None:
    adapter = LobstersAdapter(config={"tags": ["rust", "python"], "page": "hottest"})

    with patch("max.sources.lobsters.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: MOCK_STORIES)

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 2
    assert mock_fetch.call_count == 2
    assert mock_fetch.call_args_list[0].args[0] == "https://lobste.rs/t/rust.json"
    assert mock_fetch.call_args_list[1].args[0] == "https://lobste.rs/t/python.json"
    assert all(signal.source_type == SignalSourceType.TRENDING for signal in signals)


@pytest.mark.asyncio
async def test_lobsters_fetch_respects_runtime_limit() -> None:
    adapter = LobstersAdapter(config={"tags": ["rust", "python"]})

    with patch("max.sources.lobsters.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: MOCK_STORIES)

        signals = await adapter.fetch(limit=1)

    assert len(signals) == 1
    assert mock_fetch.call_count == 1
    assert signals[0].metadata["short_id"] == "abc123"


@pytest.mark.asyncio
async def test_lobsters_fetch_respects_configured_limit() -> None:
    adapter = LobstersAdapter(config={"limit": 1})

    with patch("max.sources.lobsters.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: MOCK_STORIES)

        signals = await adapter.fetch(limit=30)

    assert len(signals) == 1


@pytest.mark.asyncio
async def test_lobsters_fetch_skips_malformed_items() -> None:
    adapter = LobstersAdapter()
    stories = [
        {"short_id": "bad", "url": "https://example.com/no-title"},
        "not-a-dict",
        {
            "short_id": "ghi789",
            "title": "Valid Story",
            "score": "7",
            "comment_count": "2",
            "submitter": {"username": "carol"},
            "tags": ["programming"],
        },
    ]

    with patch("max.sources.lobsters.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: stories)

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].title == "Valid Story"
    assert signals[0].url == "https://lobste.rs/s/ghi789"
    assert signals[0].author == "carol"
    assert signals[0].metadata["score"] == 7
    assert signals[0].metadata["comment_count"] == 2
