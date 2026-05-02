"""Tests for GitHub repository topics source adapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from max.sources.errors import SourceRateLimitError
from max.sources.github_repository_topics import (
    GitHubRepositoryTopicsAdapter,
    _build_tags,
    _split_repo,
    _stable_id,
)
from max.types.signal import SignalSourceType


def _response(
    status_code: int,
    payload: dict | None = None,
    *,
    headers: dict[str, str] | None = None,
    url: str = "https://api.github.com/repos/example/tool/topics",
) -> httpx.Response:
    return httpx.Response(
        status_code,
        json=payload or {},
        headers=headers or {},
        request=httpx.Request("GET", url),
    )


def test_config_parsing_and_helpers(monkeypatch) -> None:
    monkeypatch.setenv("ALT_GITHUB_TOKEN", "env-token")
    adapter = GitHubRepositoryTopicsAdapter(
        config={
            "repositories": [" example/tool ", "example/tool", "", 42],
            "api_url": " https://github.example/api ",
            "per_page": "25",
            "timeout": "12.5",
            "token_env": "ALT_GITHUB_TOKEN",
        }
    )

    assert adapter.repositories == ["example/tool"]
    assert adapter.api_url == "https://github.example/api"
    assert adapter.per_page == 25
    assert adapter.timeout == 12.5
    assert adapter.token == "env-token"
    assert _split_repo("example/tool") == ("example", "tool")
    assert _stable_id("example/tool", ["ai", "mcp"]) == _stable_id(
        "example/tool",
        ["ai", "mcp"],
    )


def test_build_tags_normalizes_topics_and_keywords() -> None:
    tags = _build_tags("example/mcp-python", ["model-context-protocol", "developer-tools"])

    assert "repository-topics" in tags
    assert "github" in tags
    assert "mcp" in tags
    assert "python" in tags
    assert "devtools" in tags


@pytest.mark.asyncio
async def test_fetch_converts_repository_topics_to_signal() -> None:
    adapter = GitHubRepositoryTopicsAdapter(
        config={
            "repositories": ["example/tool"],
            "github_token": "configured-token",
            "per_page": 50,
            "timeout": 15,
        }
    )

    with patch("max.sources.github_repository_topics.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(
            return_value=_response(200, {"names": ["mcp", "ai", "developer-tools", "ai"]})
        )
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=10)

    mock_cls.assert_called_once()
    assert mock_cls.call_args.kwargs["timeout"] == 15
    headers = mock_cls.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer configured-token"
    assert headers["Accept"] == "application/vnd.github+json"
    mock_client.get.assert_awaited_once_with(
        "https://api.github.com/repos/example/tool/topics",
        params={"per_page": 50},
    )

    assert len(signals) == 1
    signal = signals[0]
    assert signal.id == _stable_id("example/tool", ["ai", "developer-tools", "mcp"])
    assert signal.source_type == SignalSourceType.REGISTRY
    assert signal.source_adapter == "github_repository_topics"
    assert signal.title == "example/tool repository topics"
    assert signal.content == "example/tool is positioned with ai, developer-tools, mcp."
    assert signal.url == "https://github.com/example/tool"
    assert signal.published_at is not None
    assert signal.fetched_at == signal.published_at
    assert "mcp" in signal.tags
    assert signal.metadata["repository"] == "example/tool"
    assert signal.metadata["topics"] == ["ai", "developer-tools", "mcp"]
    assert signal.metadata["topic_count"] == 3
    assert signal.metadata["source_url"] == "https://github.com/example/tool"
    assert signal.metadata["signal_role"] == "market"
    assert "configured-token" not in repr(signal.metadata)


@pytest.mark.asyncio
async def test_fetch_emits_signal_for_empty_topics() -> None:
    adapter = GitHubRepositoryTopicsAdapter(config={"repositories": ["example/untagged"]})

    with patch("max.sources.github_repository_topics.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=_response(200, {"names": []}))
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].metadata["topics"] == []
    assert signals[0].metadata["topic_count"] == 0
    assert signals[0].content == "example/untagged is positioned with no repository topics."
    assert signals[0].credibility == 0.35


@pytest.mark.asyncio
async def test_fetch_skips_404_repository() -> None:
    adapter = GitHubRepositoryTopicsAdapter(
        config={"repositories": ["example/missing", "example/tool"]}
    )

    with patch("max.sources.github_repository_topics.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(
            side_effect=[
                _response(404, {"message": "Not Found"}),
                _response(200, {"names": ["python"]}),
            ]
        )
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].metadata["repository"] == "example/tool"
    assert signals[0].metadata["topics"] == ["python"]


@pytest.mark.asyncio
async def test_fetch_rate_limit_failure_raises() -> None:
    adapter = GitHubRepositoryTopicsAdapter(config={"repositories": ["example/tool"]})

    with patch("max.sources.github_repository_topics.httpx.AsyncClient") as mock_cls, \
         patch("max.sources.retry.asyncio.sleep", new_callable=AsyncMock):
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(
            return_value=_response(
                403,
                {"message": "API rate limit exceeded"},
                headers={"X-RateLimit-Remaining": "0"},
            )
        )
        mock_cls.return_value = mock_client

        with pytest.raises(SourceRateLimitError):
            await adapter.fetch(limit=10)

    assert mock_client.get.await_count == 4


@pytest.mark.asyncio
async def test_fetch_empty_config_returns_empty_without_http() -> None:
    adapter = GitHubRepositoryTopicsAdapter(config={})

    with patch("max.sources.github_repository_topics.httpx.AsyncClient") as mock_cls:
        assert await adapter.fetch(limit=10) == []

    mock_cls.assert_not_called()
