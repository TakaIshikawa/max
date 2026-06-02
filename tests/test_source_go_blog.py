from __future__ import annotations

import pytest

from max.sources.go_blog import GoBlogAdapter, parse_go_blog


def test_go_release_posts_include_version_metadata() -> None:
    signals = parse_go_blog([
        {"title": "Go 1.24.2 is released", "url": "https://go.dev/blog/go1.24.2", "author": "Go Team", "date": "2026-05-01T00:00:00Z", "tags": ["release"]},
        {"title": "Duplicate", "url": "https://go.dev/blog/go1.24.2#comments"},
    ])

    assert len(signals) == 1
    assert signals[0].metadata["go_version"] == "1.24.2"
    assert signals[0].author == "Go Team"
    assert signals[0].tags == ["go", "release"]


def test_go_regular_posts_are_normalized() -> None:
    signals = parse_go_blog([{"title": "Profiling Go programs", "link": "https://go.dev/blog/profiling", "summary": "Tools"}])

    assert signals[0].content == "Tools"
    assert "go_version" not in signals[0].metadata


@pytest.mark.asyncio
async def test_go_adapter_empty_and_limit() -> None:
    assert await GoBlogAdapter(config={"payload": []}).fetch(limit=2) == []
    adapter = GoBlogAdapter(config={"payload": [{"title": "One", "url": "https://go.dev/blog/one"}, {"title": "Two", "url": "https://go.dev/blog/two"}]})

    assert [signal.title for signal in await adapter.fetch(limit=1)] == ["One"]
