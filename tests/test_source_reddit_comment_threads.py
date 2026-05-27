from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from max.sources.reddit_comment_threads import RedditCommentThreadsAdapter


@pytest.mark.asyncio
async def test_reddit_comment_threads_preserve_nested_and_skip_deleted() -> None:
    adapter = RedditCommentThreadsAdapter(config={"post_ids": ["abc"], "reddit_url": "https://reddit.test", "max_comments_per_thread": 10})
    payload = [
        {"data": {"children": [{"data": {"title": "Thread"}}]}},
        {"data": {"children": [{"data": {"id": "c1", "body": "valid", "score": 5, "subreddit": "python", "permalink": "/r/python/comments/abc/c1", "replies": {"data": {"children": [{"data": {"id": "c2", "body": "[deleted]"}}]}}}}]}}
    ]
    with patch("max.sources.reddit_comment_threads.httpx.AsyncClient") as cls:
        client = AsyncMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        client.get = AsyncMock(return_value=httpx.Response(200, json=payload, request=httpx.Request("GET", "https://reddit.test/comments/abc.json")))
        cls.return_value = client
        signals = await adapter.fetch(limit=5)
    assert len(signals) == 1
    assert signals[0].metadata["comment_id"] == "c1"
    assert signals[0].metadata["thread_title"] == "Thread"
