from __future__ import annotations

import pytest

from max.sources.bun_blog import BunBlogAdapter, parse_bun_blog


def test_bun_blog_parses_release_and_non_release_posts() -> None:
    signals = parse_bun_blog([{"title": "Bun v1.2.0", "url": "https://bun.sh/blog/bun-v1.2.0"}, {"title": "Using Bun", "url": "https://bun.sh/blog/using-bun"}])
    assert [signal.source_adapter for signal in signals] == ["bun_blog", "bun_blog"]
    assert signals[0].metadata["version"] == "1.2.0"


def test_bun_blog_stable_ids_and_ordering() -> None:
    payload = [{"title": "Older", "url": "https://bun.sh/old", "published_at": "2026-01-01T00:00:00Z"}, {"title": "Newer", "url": "https://bun.sh/new", "published_at": "2026-02-01T00:00:00Z"}]
    signals = parse_bun_blog(payload)
    assert signals[0].title == "Newer"
    assert parse_bun_blog(payload)[0].id == parse_bun_blog(payload)[0].id


@pytest.mark.asyncio
async def test_bun_blog_adapter_limit() -> None:
    signals = await BunBlogAdapter(config={"entries": [{"title": "A", "url": "https://b/a"}, {"title": "B", "url": "https://b/b"}]}).fetch(limit=1)
    assert len(signals) == 1
