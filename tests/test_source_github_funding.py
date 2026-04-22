"""Tests for GitHub funding source adapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from max.sources.github_funding import (
    GitHubFundingAdapter,
    _build_tags,
    _evidence_url,
    _funding_links,
)
from max.types.signal import SignalSourceType


MOCK_PROFILE = {
    "files": {
        "funding": {
            "html_url": "https://github.com/example/tool/blob/main/.github/FUNDING.yml",
        },
    },
    "funding_links": [
        {
            "platform": "GitHub Sponsors",
            "url": "https://github.com/sponsors/example",
        },
        {
            "platform": "Open Collective",
            "url": "https://opencollective.com/example-tool",
        },
        {
            "platform": "Patreon",
            "url": "https://www.patreon.com/example",
        },
        {
            "platform": "Ko-fi",
            "url": "https://ko-fi.com/example",
        },
        {
            "platform": "Custom",
            "url": "https://example.com/fund",
        },
    ],
}


def _response(payload: dict, *, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = payload
    resp.headers = {}
    resp.status_code = status_code
    resp.raise_for_status.return_value = None
    return resp


def test_funding_links_keeps_supported_platforms() -> None:
    links = _funding_links(
        {
            "funding_links": [
                {"platform": "GitHub Sponsors", "url": "https://github.com/sponsors/example"},
                {"platform": "Open Collective", "url": "https://opencollective.com/example"},
                {"platform": "Patreon", "url": "https://patreon.com/example"},
                {"platform": "Ko-fi", "url": "https://ko-fi.com/example"},
                {"platform": "Custom", "url": "https://example.com/funding"},
                {"platform": "Tidelift", "url": "https://tidelift.com/example"},
                {"platform": "", "url": "https://example.com/empty"},
                {"platform": "Custom", "url": ""},
            ],
        }
    )

    assert [link.platform for link in links] == [
        "GitHub Sponsors",
        "Open Collective",
        "Patreon",
        "Ko-fi",
        "Custom",
    ]


def test_evidence_url_prefers_funding_file() -> None:
    assert _evidence_url("example/tool", MOCK_PROFILE) == (
        "https://github.com/example/tool/blob/main/.github/FUNDING.yml"
    )
    assert _evidence_url("example/tool", {}) == "https://github.com/example/tool/community"


def test_build_tags_includes_platform() -> None:
    tags = _build_tags("Open Collective")

    assert "github" in tags
    assert "funding" in tags
    assert "sponsorship" in tags
    assert "open-collective" in tags


@pytest.mark.asyncio
async def test_github_funding_fetch_success() -> None:
    adapter = GitHubFundingAdapter(config={"repositories": ["example/tool"]})

    async def mock_get(url: str, **kwargs) -> MagicMock:
        assert url == "https://api.github.com/repos/example/tool/community/profile"
        return _response(MOCK_PROFILE)

    with patch("max.sources.github_funding.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 5
    first = signals[0]
    assert first.source_type == SignalSourceType.FUNDING
    assert first.source_adapter == "github_funding"
    assert first.title == "example/tool accepts funding via GitHub Sponsors"
    assert first.url == "https://github.com/sponsors/example"
    assert first.author == "example"
    assert first.metadata["repository"] == "example/tool"
    assert first.metadata["funding_platform"] == "GitHub Sponsors"
    assert first.metadata["funding_url"] == "https://github.com/sponsors/example"
    assert first.metadata["evidence_url"] == (
        "https://github.com/example/tool/blob/main/.github/FUNDING.yml"
    )
    assert first.metadata["signal_role"] == "market"


@pytest.mark.asyncio
async def test_github_funding_uses_configured_token() -> None:
    adapter = GitHubFundingAdapter(
        config={"repositories": ["example/tool"], "github_token": "configured-token"}
    )

    async def mock_get(url: str, **kwargs) -> MagicMock:
        return _response({"funding_links": []})

    with patch("max.sources.github_funding.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        await adapter.fetch(limit=10)

    headers = mock_cls.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer configured-token"


@pytest.mark.asyncio
async def test_github_funding_supports_unauthenticated_requests(monkeypatch) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    adapter = GitHubFundingAdapter(config={"repositories": ["example/tool"]})

    async def mock_get(url: str, **kwargs) -> MagicMock:
        return _response({"funding_links": []})

    with patch("max.sources.github_funding.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        await adapter.fetch(limit=10)

    headers = mock_cls.call_args.kwargs["headers"]
    assert "Authorization" not in headers


@pytest.mark.asyncio
async def test_github_funding_respects_limit() -> None:
    adapter = GitHubFundingAdapter(config={"repositories": ["example/tool"]})

    async def mock_get(url: str, **kwargs) -> MagicMock:
        return _response(MOCK_PROFILE)

    with patch("max.sources.github_funding.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=2)

    assert len(signals) == 2
