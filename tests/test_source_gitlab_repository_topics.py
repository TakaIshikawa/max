from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from max.sources.gitlab_repository_topics import GitLabRepositoryTopicsAdapter


@pytest.mark.asyncio
async def test_gitlab_repository_topics_request_and_metadata() -> None:
    adapter = GitLabRepositoryTopicsAdapter(config={"topics": ["mcp"], "gitlab_url": "https://gitlab.test/api/v4", "max_projects_per_topic": 2, "private_token": "secret"})
    payload = [{"id": 1, "path_with_namespace": "group/repo", "web_url": "https://gitlab/group/repo", "star_count": 8, "forks_count": 2, "last_activity_at": "2026-01-01T00:00:00Z", "namespace": {"full_path": "group"}, "topics": ["mcp"]}]
    with patch("max.sources.gitlab_repository_topics.httpx.AsyncClient") as cls:
        client = AsyncMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        client.get = AsyncMock(return_value=httpx.Response(200, json=payload, request=httpx.Request("GET", "https://gitlab.test/api/v4/projects")))
        cls.return_value = client
        signals = await adapter.fetch(limit=5)
    assert client.get.await_args.kwargs["params"]["topic"] == "mcp"
    assert cls.call_args.kwargs["headers"]["PRIVATE-TOKEN"] == "secret"
    assert signals[0].metadata["stars"] == 8
    assert signals[0].metadata["namespace"] == "group"
    assert "secret" not in repr(signals[0].metadata)
