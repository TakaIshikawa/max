from __future__ import annotations

import pytest

from max.sources.nextjs_blog import NextjsBlogAdapter, parse_nextjs_blog


def test_nextjs_release_posts_include_version_metadata() -> None:
    signals = parse_nextjs_blog([
        {"title": "Next.js 15.3", "url": "https://nextjs.org/blog/next-15-3", "summary": "Release notes", "tags": ["turbopack"]},
        {"title": "Duplicate", "url": "https://nextjs.org/blog/next-15-3?ref=feed"},
    ])

    assert len(signals) == 1
    assert signals[0].metadata["version"] == "15.3"
    assert signals[0].metadata["area"] == "turbopack"


def test_nextjs_non_release_posts_and_empty_feeds() -> None:
    signals = parse_nextjs_blog([{"title": "Building accessible forms", "link": "https://nextjs.org/blog/forms"}])

    assert signals[0].title == "Building accessible forms"
    assert "version" not in signals[0].metadata
    assert parse_nextjs_blog([]) == []


@pytest.mark.asyncio
async def test_nextjs_adapter_limit() -> None:
    adapter = NextjsBlogAdapter(config={"entries": [
        {"title": "One", "url": "https://nextjs.org/blog/one"},
        {"title": "Two", "url": "https://nextjs.org/blog/two"},
    ]})

    assert [signal.title for signal in await adapter.fetch(limit=1)] == ["One"]
