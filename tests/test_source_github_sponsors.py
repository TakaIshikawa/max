"""Tests for the GitHub Sponsors source adapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from max.sources.errors import SourceRateLimitError
from max.sources.github_sponsors import (
    GitHubSponsorsAdapter,
    _evidence_url,
    _sponsor_funding,
)
from max.types.signal import SignalSourceType


def _repo(
    full_name: str,
    *,
    stars: int = 1234,
    language: str = "Python",
    topics: list[str] | None = None,
) -> dict:
    owner, name = full_name.split("/", 1)
    return {
        "full_name": full_name,
        "name": name,
        "html_url": f"https://github.com/{full_name}",
        "description": "A useful developer tool.",
        "owner": {"login": owner},
        "stargazers_count": stars,
        "forks_count": 56,
        "language": language,
        "topics": topics or ["developer-tools", "ai-agent"],
        "open_issues_count": 7,
        "created_at": "2024-01-02T03:04:05Z",
        "updated_at": "2024-02-03T04:05:06Z",
    }


def _profile(*, funding_links: list[dict] | None = None) -> dict:
    return {
        "files": {
            "funding": {
                "html_url": "https://github.com/acme/tool/blob/main/.github/FUNDING.yml",
            },
        },
        "funding_links": funding_links
        if funding_links is not None
        else [
            {
                "platform": "GitHub Sponsors",
                "url": "https://github.com/sponsors/acme",
            },
            {
                "platform": "Open Collective",
                "url": "https://opencollective.com/acme-tool",
            },
        ],
    }


def _response(payload: object, *, status_code: int = 200, headers: dict | None = None) -> MagicMock:
    request = httpx.Request("GET", "https://api.github.com/test")
    response = httpx.Response(status_code, json=payload, headers=headers or {}, request=request)
    mock = MagicMock()
    mock.status_code = status_code
    mock.headers = response.headers
    mock.json.side_effect = response.json
    if status_code >= 400:
        mock.raise_for_status.side_effect = httpx.HTTPStatusError(
            f"HTTP {status_code}",
            request=request,
            response=response,
        )
    else:
        mock.raise_for_status.return_value = None
    return mock


def _mock_client(get):
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=get)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    return mock_client


def test_sponsor_funding_marks_github_sponsors_links() -> None:
    funding = _sponsor_funding(
        {
            "funding_links": [
                {"platform": "GitHub Sponsors", "url": "https://github.com/sponsors/acme"},
                {"platform": "Patreon", "url": "https://patreon.com/acme"},
                {"platform": "", "url": "https://example.com/empty"},
                {"platform": "Custom", "url": ""},
            ]
        },
        default_owner="fallback",
    )

    assert [(link.platform, link.maintainer, link.sponsor_enabled) for link in funding] == [
        ("GitHub Sponsors", "acme", True),
        ("Patreon", "fallback", False),
    ]


def test_evidence_url_prefers_funding_file() -> None:
    assert _evidence_url("acme/tool", _profile()) == (
        "https://github.com/acme/tool/blob/main/.github/FUNDING.yml"
    )
    assert _evidence_url("acme/tool", {}) == "https://github.com/acme/tool/community"


@pytest.mark.asyncio
async def test_fetch_repositories_emits_funding_signals() -> None:
    adapter = GitHubSponsorsAdapter(config={"repositories": ["acme/tool"]})
    requested_urls: list[str] = []

    async def get(url: str, **kwargs) -> MagicMock:
        requested_urls.append(url)
        if url.endswith("/repos/acme/tool"):
            return _response(_repo("acme/tool"))
        if url.endswith("/repos/acme/tool/community/profile"):
            return _response(_profile())
        raise AssertionError(f"unexpected URL: {url}")

    with patch("max.sources.github_sponsors.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(get)
        signals = await adapter.fetch(limit=10)

    assert requested_urls == [
        "https://api.github.com/repos/acme/tool",
        "https://api.github.com/repos/acme/tool/community/profile",
    ]
    assert len(signals) == 2
    first = signals[0]
    assert first.source_adapter == "github_sponsors"
    assert first.source_type == SignalSourceType.FUNDING
    assert first.title == "acme/tool exposes funding via GitHub Sponsors"
    assert first.url == "https://github.com/sponsors/acme"
    assert first.author == "acme"
    assert first.metadata["repository"] == "acme/tool"
    assert first.metadata["maintainer"] == "acme"
    assert first.metadata["sponsor_enabled"] is True
    assert first.metadata["funding_url"] == "https://github.com/sponsors/acme"
    assert first.metadata["stars"] == 1234
    assert first.metadata["language"] == "Python"
    assert first.metadata["evidence_url"].endswith("/.github/FUNDING.yml")
    assert {"github", "funding", "github-sponsors", "python"} <= set(first.tags)


@pytest.mark.asyncio
async def test_fetch_discovers_org_user_and_topic_repositories_with_limits() -> None:
    adapter = GitHubSponsorsAdapter(
        config={
            "organizations": ["acme"],
            "users": ["octo"],
            "topics": ["agent-tools"],
            "max_repositories_per_query": 2,
        }
    )
    requested: list[tuple[str, dict]] = []

    async def get(url: str, **kwargs) -> MagicMock:
        requested.append((url, kwargs.get("params", {})))
        if url.endswith("/orgs/acme/repos"):
            return _response([_repo("acme/org-tool")])
        if url.endswith("/users/octo/repos"):
            return _response([_repo("octo/user-tool")])
        if url.endswith("/search/repositories"):
            return _response({"items": [_repo("topic/tool")]})
        if url.endswith("/community/profile"):
            return _response(_profile())
        raise AssertionError(f"unexpected URL: {url}")

    with patch("max.sources.github_sponsors.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(get)
        signals = await adapter.fetch(limit=10)

    assert [signal.metadata["repository"] for signal in signals] == [
        "acme/org-tool",
        "acme/org-tool",
        "octo/user-tool",
        "octo/user-tool",
        "topic/tool",
        "topic/tool",
    ]
    discovery_requests = [
        item for item in requested if not item[0].endswith("/community/profile")
    ]
    assert discovery_requests[0][1]["per_page"] == 2
    assert discovery_requests[1][1]["per_page"] == 2
    assert discovery_requests[2][1]["q"] == "topic:agent-tools"
    assert discovery_requests[2][1]["per_page"] == 2


@pytest.mark.asyncio
async def test_missing_funding_data_is_skipped_without_failing() -> None:
    adapter = GitHubSponsorsAdapter(config={"repositories": ["acme/tool", "acme/funded"]})

    async def get(url: str, **kwargs) -> MagicMock:
        if url.endswith("/repos/acme/tool"):
            return _response(_repo("acme/tool"))
        if url.endswith("/repos/acme/funded"):
            return _response(_repo("acme/funded"))
        if url.endswith("/repos/acme/tool/community/profile"):
            return _response(_profile(funding_links=[]))
        if url.endswith("/repos/acme/funded/community/profile"):
            return _response(_profile())
        raise AssertionError(f"unexpected URL: {url}")

    with patch("max.sources.github_sponsors.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(get)
        signals = await adapter.fetch(limit=10)

    assert [signal.metadata["repository"] for signal in signals] == [
        "acme/funded",
        "acme/funded",
    ]


@pytest.mark.asyncio
async def test_deduplicates_repositories_and_funding_urls() -> None:
    adapter = GitHubSponsorsAdapter(
        config={"repositories": ["acme/tool"], "topics": ["developer-tools"]}
    )

    async def get(url: str, **kwargs) -> MagicMock:
        if url.endswith("/repos/acme/tool"):
            return _response(_repo("acme/tool"))
        if url.endswith("/search/repositories"):
            return _response({"items": [_repo("acme/tool")]})
        if url.endswith("/repos/acme/tool/community/profile"):
            return _response(
                _profile(
                    funding_links=[
                        {
                            "platform": "GitHub Sponsors",
                            "url": "https://github.com/sponsors/acme",
                        },
                        {
                            "platform": "GitHub Sponsors",
                            "url": "https://github.com/sponsors/acme",
                        },
                    ]
                )
            )
        raise AssertionError(f"unexpected URL: {url}")

    with patch("max.sources.github_sponsors.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(get)
        signals = await adapter.fetch(limit=10)

    assert [signal.url for signal in signals] == ["https://github.com/sponsors/acme"]


@pytest.mark.asyncio
async def test_fetch_respects_signal_limit() -> None:
    adapter = GitHubSponsorsAdapter(config={"repositories": ["acme/tool"]})

    async def get(url: str, **kwargs) -> MagicMock:
        if url.endswith("/repos/acme/tool"):
            return _response(_repo("acme/tool"))
        if url.endswith("/repos/acme/tool/community/profile"):
            return _response(_profile())
        raise AssertionError(f"unexpected URL: {url}")

    with patch("max.sources.github_sponsors.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(get)
        signals = await adapter.fetch(limit=1)

    assert len(signals) == 1
    assert signals[0].url == "https://github.com/sponsors/acme"


@pytest.mark.asyncio
async def test_supports_unauthenticated_requests(monkeypatch) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    adapter = GitHubSponsorsAdapter(config={"repositories": ["acme/tool"]})

    async def get(url: str, **kwargs) -> MagicMock:
        if url.endswith("/repos/acme/tool"):
            return _response(_repo("acme/tool"))
        if url.endswith("/repos/acme/tool/community/profile"):
            return _response(_profile(funding_links=[]))
        raise AssertionError(f"unexpected URL: {url}")

    with patch("max.sources.github_sponsors.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(get)
        await adapter.fetch(limit=10)

    assert "Authorization" not in mock_cls.call_args.kwargs["headers"]


@pytest.mark.asyncio
async def test_rate_limit_response_raises_typed_error() -> None:
    adapter = GitHubSponsorsAdapter(config={"repositories": ["acme/tool"]})

    async def get(url: str, **kwargs) -> MagicMock:
        return _response(
            {"message": "API rate limit exceeded"},
            status_code=403,
            headers={"X-RateLimit-Remaining": "0", "Retry-After": "0"},
        )

    with (
        patch("max.sources.github_sponsors.httpx.AsyncClient") as mock_cls,
        patch("max.sources.retry.asyncio.sleep", new_callable=AsyncMock),
    ):
        mock_cls.return_value = _mock_client(get)
        with pytest.raises(SourceRateLimitError):
            await adapter.fetch(limit=10)
