"""Tests for the GitHub Trending source adapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from max.sources.base import _circuit_breakers
from max.sources.github_trending import GitHubTrendingAdapter
from max.types.signal import SignalSourceType


@pytest.fixture(autouse=True)
def _reset_circuit_breakers() -> None:
    _circuit_breakers.clear()


def _response(html: str) -> MagicMock:
    response = MagicMock()
    response.status_code = 200
    response.text = html
    return response


def _mock_client(request):
    mock_client = AsyncMock()
    mock_client.request = AsyncMock(side_effect=request)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    return mock_client


def _repo_html(
    owner: str,
    name: str,
    *,
    description: str = "A useful developer tool.",
    stars: str = "1,234",
    forks: str = "56",
    language: str = "Python",
    stars_today: str = "12 stars today",
) -> str:
    return f"""
    <article class="Box-row">
      <h2><a href="/{owner}/{name}"> {owner} / {name} </a></h2>
      <p>{description}</p>
      <span itemprop="programmingLanguage">{language}</span>
      <a href="/{owner}/{name}/stargazers">{stars}</a>
      <a href="/{owner}/{name}/forks">{forks}</a>
      <span class="d-inline-block float-sm-right">{stars_today}</span>
    </article>
    """


@pytest.mark.asyncio
async def test_fetch_default_trending_page_returns_normalized_signals() -> None:
    adapter = GitHubTrendingAdapter()

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        assert method == "GET"
        assert url == "https://github.com/trending?since=daily"
        return _response(_repo_html("acme", "agent-kit"))

    with patch("max.sources.github_trending.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    signal = signals[0]
    assert signal.source_adapter == "github_trending"
    assert signal.source_type == SignalSourceType.TRENDING
    assert signal.title == "acme/agent-kit"
    assert signal.content == "A useful developer tool."
    assert signal.url == "https://github.com/acme/agent-kit"
    assert signal.author == "acme"
    assert signal.metadata["repository"] == "acme/agent-kit"
    assert signal.metadata["stars"] == 1234
    assert signal.metadata["forks"] == 56
    assert signal.metadata["language"] == "Python"
    assert signal.metadata["stars_today"] == 12
    assert signal.metadata["since"] == "daily"
    assert signal.metadata["signal_role"] == "market"
    assert {"github", "trending", "repository", "python"} <= set(signal.tags)


@pytest.mark.asyncio
async def test_fetch_custom_languages_since_base_url_and_topics() -> None:
    adapter = GitHubTrendingAdapter(
        config={
            "languages": ["python", "typescript"],
            "since": "weekly",
            "base_url": "https://example.test",
            "topics": ["agentic ai"],
        }
    )
    requested_urls: list[str] = []

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        requested_urls.append(url)
        if url.endswith("/trending/python?since=weekly"):
            return _response(_repo_html("py", "tool", language="Python"))
        if url.endswith("/trending/typescript?since=weekly"):
            return _response(_repo_html("ts", "app", language="TypeScript"))
        raise AssertionError(f"unexpected URL: {url}")

    with patch("max.sources.github_trending.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=10)

    assert requested_urls == [
        "https://example.test/trending/python?since=weekly",
        "https://example.test/trending/typescript?since=weekly",
    ]
    assert [signal.title for signal in signals] == ["py/tool", "ts/app"]
    assert signals[0].metadata["trending_language"] == "python"
    assert signals[1].metadata["trending_language"] == "typescript"
    assert signals[0].metadata["topics"] == ["agentic ai"]
    assert "agentic-ai" in signals[0].tags


@pytest.mark.asyncio
async def test_duplicate_repositories_across_languages_are_emitted_once() -> None:
    adapter = GitHubTrendingAdapter(config={"languages": ["python", "go"]})

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        if url.endswith("/trending/python?since=daily"):
            return _response(_repo_html("acme", "shared", language="Python"))
        if url.endswith("/trending/go?since=daily"):
            return _response(
                _repo_html("acme", "shared", language="Go")
                + _repo_html("other", "unique", language="Go")
            )
        raise AssertionError(f"unexpected URL: {url}")

    with patch("max.sources.github_trending.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=10)

    assert [signal.title for signal in signals] == ["acme/shared", "other/unique"]


@pytest.mark.asyncio
async def test_fetch_respects_limit_across_pages() -> None:
    adapter = GitHubTrendingAdapter(config={"languages": ["python", "go"]})
    requested_urls: list[str] = []

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        requested_urls.append(url)
        return _response(
            _repo_html("one", "repo", language="Python")
            + _repo_html("two", "repo", language="Python")
        )

    with patch("max.sources.github_trending.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=1)

    assert [signal.title for signal in signals] == ["one/repo"]
    assert requested_urls == ["https://github.com/trending/python?since=daily"]


@pytest.mark.asyncio
async def test_malformed_or_empty_html_is_skipped_without_failing_fetch() -> None:
    adapter = GitHubTrendingAdapter(config={"languages": ["broken", "empty", "python"]})

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        if url.endswith("/trending/broken?since=daily"):
            return _response("<article class='Box-row'><h2>missing link</h2></article>")
        if url.endswith("/trending/empty?since=daily"):
            return _response("")
        if url.endswith("/trending/python?since=daily"):
            return _response(_repo_html("valid", "repo", language="Python"))
        raise AssertionError(f"unexpected URL: {url}")

    with patch("max.sources.github_trending.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=10)

    assert [signal.title for signal in signals] == ["valid/repo"]
