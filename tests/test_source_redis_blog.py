from __future__ import annotations

import pytest

from max.sources.redis_blog import RedisBlogAdapter, parse_redis_blog


def test_redis_blog_normalizes_topics_author_and_date() -> None:
    signals = parse_redis_blog([
        {"title": "Vector search in Redis Cloud", "url": "https://redis.io/blog/vector-search", "author": "Dana", "date": "2026-05-10T00:00:00Z", "categories": ["Search", "Cloud"]},
        {"title": "Duplicate", "url": "https://redis.io/blog/vector-search#comments"},
    ])

    assert len(signals) == 1
    assert signals[0].author == "Dana"
    assert signals[0].metadata["topics"] == ["vector", "search", "cloud"]
    assert signals[0].tags == ["redis", "Search", "Cloud"]


@pytest.mark.asyncio
async def test_redis_blog_dedupes_and_honors_limit() -> None:
    adapter = RedisBlogAdapter(config={"entries": [
        {"title": "Cache patterns", "url": "https://redis.io/blog/cache"},
        {"title": "Streams patterns", "url": "https://redis.io/blog/streams"},
    ]})

    assert [signal.title for signal in await adapter.fetch(limit=1)] == ["Cache patterns"]


def test_redis_blog_empty_feed() -> None:
    assert parse_redis_blog([]) == []
