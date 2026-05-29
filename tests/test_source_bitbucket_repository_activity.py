from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from max.sources.bitbucket_repository_activity import BitbucketRepositoryActivityAdapter


@pytest.mark.asyncio
async def test_bitbucket_repository_activity_handles_pagination_and_defaults() -> None:
    adapter = BitbucketRepositoryActivityAdapter(config={"workspaces": ["team"], "project_keys": ["PRJ"], "queries": ["sdk"], "bitbucket_url": "https://bb.test"})
    first = {"values": [{"uuid": "{1}", "full_name": "team/repo", "updated_on": "2026-01-01T00:00:00Z", "links": {"html": {"href": "https://bb/team/repo"}}}], "next": "https://bb.test/page2"}
    second = {"values": [{"uuid": "{2}", "full_name": "team/repo2"}]}
    with patch("max.sources.bitbucket_repository_activity.httpx.AsyncClient") as cls:
        client = AsyncMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        client.get = AsyncMock(side_effect=[
            httpx.Response(200, json=first, request=httpx.Request("GET", "https://bb.test/repositories/team")),
            httpx.Response(200, json=second, request=httpx.Request("GET", "https://bb.test/page2")),
        ])
        cls.return_value = client
        signals = await adapter.fetch(limit=5)
    assert len(signals) == 2
    assert "project.key" in client.get.await_args_list[0].kwargs["params"]["q"]
    assert signals[1].metadata["fork_count"] == 0
