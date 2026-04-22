"""Tests for GitHub releases source adapter."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from max.sources.errors import SourceRateLimitError
from max.sources.github_releases import (
    GitHubReleasesAdapter,
    _build_tags,
    _next_link,
    _page_from_url,
    _parse_dt,
)
from max.types.signal import SignalSourceType


MOCK_RELEASE = {
    "id": 1001,
    "html_url": "https://github.com/example/tool/releases/tag/v1.0.0",
    "tag_name": "v1.0.0",
    "name": "v1.0.0",
    "body": "Release notes with AI agent workflow improvements.",
    "draft": False,
    "prerelease": False,
    "created_at": "2026-04-10T12:00:00Z",
    "published_at": "2026-04-11T12:00:00Z",
    "author": {"login": "maintainer"},
    "reactions": {"total_count": 8},
}


def _response(
    payload: list[dict],
    *,
    headers: dict[str, str] | None = None,
    status_code: int = 200,
) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = payload
    resp.headers = headers or {}
    resp.status_code = status_code
    resp.raise_for_status.return_value = None
    return resp


def test_parse_dt_valid_iso8601() -> None:
    dt = _parse_dt("2026-04-11T12:00:00Z")
    assert isinstance(dt, datetime)
    assert dt.year == 2026
    assert dt.tzinfo is not None


def test_parse_dt_invalid_or_missing() -> None:
    assert _parse_dt(None) is None
    assert _parse_dt("not a date") is None


def test_next_link_parses_link_header() -> None:
    header = (
        '<https://api.github.com/repos/example/tool/releases?page=2>; rel="next", '
        '<https://api.github.com/repos/example/tool/releases?page=4>; rel="last"'
    )
    assert _next_link(header) == "https://api.github.com/repos/example/tool/releases?page=2"
    assert _page_from_url(_next_link(header) or "") == 2


def test_build_tags_extracts_release_keywords() -> None:
    tags = _build_tags(
        "example/mcp-python",
        {"name": "Agent SDK", "tag_name": "v1", "body": "MCP and LLM updates"},
    )
    assert "release" in tags
    assert "mcp" in tags
    assert "agent" in tags
    assert "llm" in tags
    assert "python" in tags


@pytest.mark.asyncio
async def test_github_releases_fetch_success() -> None:
    adapter = GitHubReleasesAdapter(config={"repositories": ["example/tool"]})

    async def mock_get(url: str, **kwargs) -> MagicMock:
        assert url == "https://api.github.com/repos/example/tool/releases"
        assert kwargs["params"]["page"] == 1
        return _response([MOCK_RELEASE])

    with patch("max.sources.github_releases.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    signal = signals[0]
    assert signal.source_type == SignalSourceType.ROADMAP
    assert signal.source_adapter == "github_releases"
    assert signal.title == "example/tool v1.0.0"
    assert "AI agent workflow" in signal.content
    assert signal.url == "https://github.com/example/tool/releases/tag/v1.0.0"
    assert signal.author == "maintainer"
    assert signal.published_at is not None
    assert "release" in signal.tags
    assert signal.metadata["github_release_id"] == 1001
    assert signal.metadata["repo"] == "example/tool"
    assert signal.metadata["tag_name"] == "v1.0.0"


@pytest.mark.asyncio
async def test_github_releases_uses_configured_token() -> None:
    adapter = GitHubReleasesAdapter(
        config={"repositories": ["example/tool"], "github_token": "configured-token"}
    )

    async def mock_get(url: str, **kwargs) -> MagicMock:
        return _response([])

    with patch("max.sources.github_releases.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        await adapter.fetch(limit=10)

    mock_cls.assert_called_once()
    headers = mock_cls.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer configured-token"


@pytest.mark.asyncio
async def test_github_releases_supports_unauthenticated_requests(monkeypatch) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    adapter = GitHubReleasesAdapter(config={"repositories": ["example/tool"]})

    async def mock_get(url: str, **kwargs) -> MagicMock:
        return _response([])

    with patch("max.sources.github_releases.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        await adapter.fetch(limit=10)

    headers = mock_cls.call_args.kwargs["headers"]
    assert "Authorization" not in headers


@pytest.mark.asyncio
async def test_github_releases_uses_environment_token(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "env-token")
    adapter = GitHubReleasesAdapter(config={"repositories": ["example/tool"]})

    async def mock_get(url: str, **kwargs) -> MagicMock:
        return _response([])

    with patch("max.sources.github_releases.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        await adapter.fetch(limit=10)

    headers = mock_cls.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer env-token"


@pytest.mark.asyncio
async def test_github_releases_follows_pagination() -> None:
    adapter = GitHubReleasesAdapter(config={"repositories": ["example/tool"]})
    release_2 = {
        **MOCK_RELEASE,
        "id": 1002,
        "html_url": "https://github.com/example/tool/releases/tag/v1.1.0",
        "tag_name": "v1.1.0",
        "name": "v1.1.0",
    }
    responses = [
        _response(
            [MOCK_RELEASE],
            headers={
                "Link": (
                    '<https://api.github.com/repos/example/tool/releases?per_page=2&page=2>; '
                    'rel="next"'
                )
            },
        ),
        _response([release_2]),
    ]
    requested_pages: list[int] = []

    async def mock_get(url: str, **kwargs) -> MagicMock:
        requested_pages.append(kwargs["params"]["page"])
        return responses.pop(0)

    with patch("max.sources.github_releases.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=2)

    assert requested_pages == [1, 2]
    assert len(signals) == 2
    assert {s.metadata["tag_name"] for s in signals} == {"v1.0.0", "v1.1.0"}


@pytest.mark.asyncio
async def test_github_releases_missing_body_falls_back_to_title() -> None:
    adapter = GitHubReleasesAdapter(config={"repositories": ["example/tool"]})
    release = {
        **MOCK_RELEASE,
        "body": None,
        "name": "Stable Release",
        "tag_name": "v2.0.0",
    }

    async def mock_get(url: str, **kwargs) -> MagicMock:
        return _response([release])

    with patch("max.sources.github_releases.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].title == "example/tool Stable Release (v2.0.0)"
    assert signals[0].content == signals[0].title


@pytest.mark.asyncio
async def test_github_releases_filters_drafts_and_prereleases_by_default() -> None:
    adapter = GitHubReleasesAdapter(config={"repositories": ["example/tool"]})
    draft = {
        **MOCK_RELEASE,
        "id": 1002,
        "html_url": "https://github.com/example/tool/releases/tag/v1.1.0",
        "draft": True,
    }
    prerelease = {
        **MOCK_RELEASE,
        "id": 1003,
        "html_url": "https://github.com/example/tool/releases/tag/v1.2.0-beta",
        "prerelease": True,
    }

    async def mock_get(url: str, **kwargs) -> MagicMock:
        return _response([draft, prerelease, MOCK_RELEASE])

    with patch("max.sources.github_releases.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].metadata["github_release_id"] == 1001


@pytest.mark.asyncio
async def test_github_releases_can_include_drafts_and_prereleases() -> None:
    adapter = GitHubReleasesAdapter(
        config={
            "repositories": ["example/tool"],
            "include_drafts": True,
            "include_prereleases": True,
        }
    )
    draft = {
        **MOCK_RELEASE,
        "id": 1002,
        "html_url": "https://github.com/example/tool/releases/tag/v1.1.0",
        "draft": True,
    }
    prerelease = {
        **MOCK_RELEASE,
        "id": 1003,
        "html_url": "https://github.com/example/tool/releases/tag/v1.2.0-beta",
        "prerelease": True,
    }

    async def mock_get(url: str, **kwargs) -> MagicMock:
        return _response([draft, prerelease, MOCK_RELEASE])

    with patch("max.sources.github_releases.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 3
    assert {s.metadata["github_release_id"] for s in signals} == {1001, 1002, 1003}


@pytest.mark.asyncio
async def test_github_releases_rate_limit_failure_raises() -> None:
    adapter = GitHubReleasesAdapter(config={"repositories": ["example/tool"]})
    call_count = 0

    async def mock_get(url: str, **kwargs) -> MagicMock:
        nonlocal call_count
        call_count += 1
        response = MagicMock(status_code=429, headers={"Retry-After": "0"})
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "429 Too Many Requests",
            request=MagicMock(),
            response=response,
        )
        return response

    with patch("max.sources.github_releases.httpx.AsyncClient") as mock_cls, \
         patch("max.sources.retry.asyncio.sleep", new_callable=AsyncMock):
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        with pytest.raises(SourceRateLimitError):
            await adapter.fetch(limit=10)

    assert call_count == 4
