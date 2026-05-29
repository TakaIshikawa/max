from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from max.sources.github_code_search import GitHubCodeSearchAdapter


@pytest.mark.asyncio
async def test_github_code_search_query_and_secret_handling() -> None:
    adapter = GitHubCodeSearchAdapter(config={"queries": ["deprecated"], "repositories": ["o/r"], "languages": ["Python"], "github_token": "secret", "github_api_url": "https://gh.test"})
    payload = {"items": [{"path": "a.py", "html_url": "https://gh/o/r/a.py", "score": 3, "repository": {"full_name": "o/r"}}]}
    with patch("max.sources.github_code_search.httpx.AsyncClient") as cls:
        client = AsyncMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        client.get = AsyncMock(return_value=httpx.Response(200, json=payload, request=httpx.Request("GET", "https://gh.test/search/code")))
        cls.return_value = client
        signals = await adapter.fetch(limit=5)
    assert client.get.await_args.kwargs["params"]["q"] == "deprecated repo:o/r language:Python"
    assert cls.call_args.kwargs["headers"]["Authorization"] == "Bearer secret"
    assert signals[0].metadata["repository"] == "o/r"
    assert signals[0].metadata["html_url"] == "https://gh/o/r/a.py"
    assert "secret" not in repr(signals[0].metadata)
