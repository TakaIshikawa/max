"""Tests for the Lobsters import source adapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from max.imports.lobsters_adapter import LobstersAdapter
from max.sources.base import AdapterFetchError
from max.types.signal import SignalSourceType


def _response(payload: object) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = payload
    return resp


def _story(
    short_id: str = "abc123",
    *,
    title: str = "Rust Async Debugging Tools",
    score: int = 42,
    comment_count: int = 9,
    tags: list[str] | None = None,
    comments: list[dict] | None = None,
) -> dict:
    story = {
        "short_id": short_id,
        "title": title,
        "url": f"https://example.com/{short_id}",
        "comments_url": f"https://lobste.rs/s/{short_id}/{title.lower().replace(' ', '_')}",
        "score": score,
        "comment_count": comment_count,
        "submitter_user": {"username": "alice"},
        "tags": tags or ["rust", "debugging"],
        "created_at": "2026-04-21T10:30:00Z",
    }
    if comments is not None:
        story["comments"] = comments
    return story


def _comment(comment_id: str = "c1") -> dict:
    return {
        "short_id": comment_id,
        "comment": "<p>This captures real debugging pain.</p>",
        "score": 7,
        "user": "bob",
        "created_at": "2026-04-21T11:30:00Z",
    }


def test_lobsters_adapter_properties() -> None:
    adapter = LobstersAdapter(config={"pages": ["hottest"], "tags": ["rust"]})

    assert adapter.name == "lobsters_import"
    assert adapter.source_type == SignalSourceType.FORUM.value
    assert adapter.pages == ["hottest"]
    assert adapter.tags == ["rust"]


@pytest.mark.asyncio
async def test_lobsters_fetches_hottest_and_newest_stories() -> None:
    adapter = LobstersAdapter(config={"include_comments": False})

    with patch("max.imports.lobsters_adapter.fetch_with_retry", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.side_effect = [
            _response([_story("hot1", title="Hot compiler work")]),
            _response([_story("new1", title="New database tool", score=13, comment_count=4)]),
        ]

        signals = await adapter.fetch(limit=10)

    assert [call.args[0] for call in mock_fetch.call_args_list] == [
        "https://lobste.rs/hottest.json",
        "https://lobste.rs/newest.json",
    ]
    assert len(signals) == 2
    assert signals[0].source_type == SignalSourceType.TRENDING
    assert signals[0].source_adapter == "lobsters_import"
    assert signals[0].title == "Hot compiler work"
    assert signals[0].author == "alice"
    assert signals[0].metadata["score"] == 42
    assert signals[0].metadata["comment_count"] == 9
    assert "rust" in signals[0].tags


@pytest.mark.asyncio
async def test_lobsters_fetches_tag_pages_with_pagination() -> None:
    adapter = LobstersAdapter(
        config={"tags": ["rust"], "pages": [], "max_pages": 2, "include_comments": False},
    )

    with patch("max.imports.lobsters_adapter.fetch_with_retry", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.side_effect = [
            _response([_story("page1")]),
            _response([_story("page2")]),
            _response([]),
            _response([]),
        ]

        signals = await adapter.fetch(limit=10)

    assert mock_fetch.call_args_list[0].args[0] == "https://lobste.rs/t/rust.json"
    assert mock_fetch.call_args_list[0].kwargs["params"] is None
    assert mock_fetch.call_args_list[1].args[0] == "https://lobste.rs/t/rust.json"
    assert mock_fetch.call_args_list[1].kwargs["params"] == {"page": 2}
    assert [signal.metadata["short_id"] for signal in signals] == ["page1", "page2"]


@pytest.mark.asyncio
async def test_lobsters_extracts_inline_comments() -> None:
    adapter = LobstersAdapter(config={"pages": ["newest"]})

    with patch("max.imports.lobsters_adapter.fetch_with_retry", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = _response([_story("abc123", comments=[_comment("xyz")])])

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 2
    comment = signals[1]
    assert comment.source_type == SignalSourceType.FORUM
    assert comment.title == "Comment on Rust Async Debugging Tools"
    assert comment.content == "This captures real debugging pain."
    assert comment.url.endswith("#c_xyz")
    assert comment.author == "bob"
    assert comment.metadata["lobsters_type"] == "comment"


@pytest.mark.asyncio
async def test_lobsters_fetches_comments_endpoint_when_not_embedded() -> None:
    adapter = LobstersAdapter(config={"pages": ["newest"]})

    with patch("max.imports.lobsters_adapter.fetch_with_retry", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.side_effect = [
            _response([_story("abc123")]),
            _response({"comments": [_comment("fetched")]}),
        ]

        signals = await adapter.fetch(limit=10)

    assert mock_fetch.call_args_list[1].args[0] == (
        "https://lobste.rs/s/abc123/rust_async_debugging_tools.json"
    )
    assert len(signals) == 2
    assert signals[1].metadata["comment_id"] == "fetched"


@pytest.mark.asyncio
async def test_lobsters_handles_empty_and_malformed_responses_gracefully() -> None:
    adapter = LobstersAdapter(config={"pages": ["newest"], "include_comments": False})

    with patch("max.imports.lobsters_adapter.fetch_with_retry", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = _response([
            {},
            "not a dict",
            _story("valid", title="Valid story"),
        ])

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].title == "Valid story"


@pytest.mark.asyncio
async def test_lobsters_handles_fetch_errors_gracefully() -> None:
    adapter = LobstersAdapter(config={"pages": ["newest"]})

    with patch("max.imports.lobsters_adapter.fetch_with_retry", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.side_effect = AdapterFetchError("lobsters_import", 500, "https://lobste.rs/newest.json")

        signals = await adapter.fetch(limit=10)

    assert signals == []
