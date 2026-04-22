"""Tests for the Discourse source adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from max.sources.discourse import DiscourseAdapter
from max.types.signal import SignalSourceType


def _response(data: dict) -> MagicMock:
    return MagicMock(json=lambda: data)


def _topic(
    topic_id: int,
    *,
    title: str = "Discourse Topic",
    slug: str = "discourse-topic",
    category_id: int = 7,
    reply_count: int = 4,
    views: int = 250,
    like_count: int = 6,
) -> dict:
    return {
        "id": topic_id,
        "title": title,
        "slug": slug,
        "category_id": category_id,
        "created_at": "2026-04-22T10:30:00.000Z",
        "reply_count": reply_count,
        "views": views,
        "like_count": like_count,
        "tags": ["roadmap", "feedback"],
        "posters": [{"user_id": 11, "description": "Original Poster"}],
    }


def _topic_list(topics: list[dict], *, more_topics_url: str | None = None) -> dict:
    topic_list = {"topics": topics}
    if more_topics_url is not None:
        topic_list["more_topics_url"] = more_topics_url
    return {
        "users": [{"id": 11, "username": "alice"}],
        "topic_list": topic_list,
    }


class TestDiscourseAdapter:
    def test_name_source_type_and_config(self) -> None:
        adapter = DiscourseAdapter(config={
            "base_urls": ["https://meta.discourse.org/"],
            "category_slugs": ["support", "/dev/plugins/"],
            "tags": ["community"],
            "max_pages": "2",
        })

        assert adapter.name == "discourse"
        assert adapter.source_type == SignalSourceType.FORUM.value
        assert adapter.base_urls == ["https://meta.discourse.org"]
        assert adapter.category_slugs == ["support", "dev/plugins"]
        assert adapter.tags == ["community"]
        assert adapter.max_pages == 2

    @pytest.mark.asyncio
    async def test_fetch_parses_latest_topics_from_multiple_forums(self) -> None:
        adapter = DiscourseAdapter(config={
            "base_urls": ["https://forum.one.example", "https://forum.two.example/"],
            "tags": ["community"],
        })

        responses = [
            _response(_topic_list([_topic(101, title="First Forum Topic")])),
            _response(_topic_list([_topic(201, title="Second Forum Topic", slug="second-topic")])),
        ]

        with patch("max.sources.discourse.fetch_with_retry", side_effect=responses) as mock_fetch:
            signals = await adapter.fetch(limit=10)

        assert len(signals) == 2
        assert mock_fetch.call_args_list[0].args[0] == "https://forum.one.example/latest.json"
        assert mock_fetch.call_args_list[1].args[0] == "https://forum.two.example/latest.json"
        assert mock_fetch.call_args_list[0].kwargs["params"] == {"page": 0}

        first = signals[0]
        assert first.source_type == SignalSourceType.FORUM
        assert first.source_adapter == "discourse"
        assert first.title == "First Forum Topic"
        assert first.content == "First Forum Topic"
        assert first.url == "https://forum.one.example/t/discourse-topic/101"
        assert first.author == "alice"
        assert first.published_at == datetime(2026, 4, 22, 10, 30, tzinfo=timezone.utc)
        assert first.tags == ["community", "roadmap", "feedback", "discourse"]
        assert first.metadata["forum"] == "forum.one.example"
        assert first.metadata["category"] == 7
        assert first.metadata["reply_count"] == 4
        assert first.metadata["views"] == 250
        assert first.metadata["like_count"] == 6

    @pytest.mark.asyncio
    async def test_fetch_uses_category_filters(self) -> None:
        adapter = DiscourseAdapter(config={
            "base_urls": ["https://meta.discourse.org"],
            "category_slugs": ["support", "dev/plugins"],
        })

        with patch("max.sources.discourse.fetch_with_retry") as mock_fetch:
            mock_fetch.return_value = _response(_topic_list([_topic(301)]))

            signals = await adapter.fetch(limit=10)

        assert len(signals) == 1
        assert mock_fetch.call_args_list[0].args[0] == "https://meta.discourse.org/c/support.json"
        assert mock_fetch.call_args_list[1].args[0] == "https://meta.discourse.org/c/dev/plugins.json"
        assert signals[0].metadata["category"] == "support"

    @pytest.mark.asyncio
    async def test_fetch_handles_missing_optional_fields(self) -> None:
        adapter = DiscourseAdapter(config={"base_urls": ["https://forum.example"]})
        sparse_topic = {
            "id": 401,
            "title": "Sparse Public Topic",
            "slug": "sparse-public-topic",
        }

        with patch("max.sources.discourse.fetch_with_retry") as mock_fetch:
            mock_fetch.return_value = _response(_topic_list([sparse_topic]))

            signals = await adapter.fetch(limit=10)

        assert len(signals) == 1
        signal = signals[0]
        assert signal.title == "Sparse Public Topic"
        assert signal.author is None
        assert signal.published_at is None
        assert signal.credibility == pytest.approx(0.2)
        assert signal.metadata["forum"] == "forum.example"
        assert signal.metadata["category"] is None
        assert "reply_count" not in signal.metadata
        assert "views" not in signal.metadata
        assert "like_count" not in signal.metadata

    @pytest.mark.asyncio
    async def test_fetch_respects_pagination_limit_and_signal_limit(self) -> None:
        adapter = DiscourseAdapter(config={
            "base_urls": ["https://forum.example"],
            "max_pages": 2,
        })

        page_0 = _topic_list(
            [_topic(501, title="Page Zero")],
            more_topics_url="/latest.json?page=1",
        )
        page_1 = _topic_list(
            [_topic(502, title="Page One")],
            more_topics_url="/latest.json?page=2",
        )

        with patch("max.sources.discourse.fetch_with_retry", side_effect=[
            _response(page_0),
            _response(page_1),
        ]) as mock_fetch:
            signals = await adapter.fetch(limit=10)

        assert len(signals) == 2
        assert mock_fetch.call_count == 2
        assert mock_fetch.call_args_list[0].kwargs["params"] == {"page": 0}
        assert mock_fetch.call_args_list[1].kwargs["params"] == {"page": 1}

        with patch("max.sources.discourse.fetch_with_retry", return_value=_response(page_0)) as mock_fetch:
            limited = await adapter.fetch(limit=1)

        assert len(limited) == 1
        assert mock_fetch.call_count == 1
