from __future__ import annotations

import pytest

from max.sources.temporal_blog import TemporalBlogAdapter, parse_temporal_blog


def test_temporal_blog_normalizes_feed_entries() -> None:
    signals = parse_temporal_blog([{"title": "Workflow update", "url": "https://temporal.io/blog/workflow", "published_at": "2026-05-01T00:00:00Z"}])
    assert signals[0].source_adapter == "temporal_blog"
    assert signals[0].published_at is not None


def test_temporal_blog_optional_category_metadata() -> None:
    signal = parse_temporal_blog([{"title": "SDK release", "url": "https://temporal.io/blog/sdk", "sdk": "python", "cloud": "temporal cloud"}])[0]
    assert signal.metadata["sdk"] == "python"
    assert signal.metadata["cloud"] == "temporal cloud"


def test_temporal_blog_stable_ids() -> None:
    payload = [{"title": "A", "url": "https://temporal/a"}]
    assert parse_temporal_blog(payload)[0].id == parse_temporal_blog(payload)[0].id


@pytest.mark.asyncio
async def test_temporal_blog_adapter_limit() -> None:
    signals = await TemporalBlogAdapter(config={"entries": [{"title": "A", "url": "https://t/a"}, {"title": "B", "url": "https://t/b"}]}).fetch(limit=1)
    assert len(signals) == 1
