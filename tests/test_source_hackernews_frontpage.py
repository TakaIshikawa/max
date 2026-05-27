from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from max.sources.hackernews_frontpage import HackerNewsFrontpageAdapter


@pytest.mark.asyncio
async def test_hackernews_frontpage_fetches_and_filters_items() -> None:
    adapter = HackerNewsFrontpageAdapter(config={"hn_api_url": "https://hn.test", "max_items": 2, "min_score": 10, "include_text": True})
    with patch("max.sources.hackernews_frontpage.httpx.AsyncClient") as cls:
        client = AsyncMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        client.get = AsyncMock(side_effect=[
            httpx.Response(200, json=[1, 2], request=httpx.Request("GET", "https://hn.test/topstories.json")),
            httpx.Response(200, json={"id": 1, "title": "Low", "score": 1}, request=httpx.Request("GET", "https://hn.test/item/1.json")),
            httpx.Response(200, json={"id": 2, "title": "High", "score": 20, "descendants": 5, "url": "https://x", "text": "body"}, request=httpx.Request("GET", "https://hn.test/item/2.json")),
        ])
        cls.return_value = client
        signals = await adapter.fetch(limit=5)
    assert len(signals) == 1
    assert signals[0].metadata["external_url"] == "https://x"
    assert signals[0].metadata["hn_url"] == "https://news.ycombinator.com/item?id=2"
