"""Tests for GitHub Pull Requests source adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from max.sources.github_pull_requests import (
    GitHubPullRequestsAdapter,
    _build_tags,
    _parse_dt,
    _pr_query,
)
from max.types.signal import SignalSourceType


MOCK_PULL = {
    "id": 1001,
    "node_id": "PR_kwDOExample",
    "number": 42,
    "title": "Fix MCP agent integration failure",
    "body": "This fixes a broken LLM agent workflow and adds safer retries.",
    "html_url": "https://github.com/example/tool/pull/42",
    "repository_url": "https://api.github.com/repos/example/tool",
    "state": "open",
    "labels": [{"name": "bug"}, {"name": "integration"}],
    "comments": 8,
    "review_comments": 3,
    "commits": 2,
    "additions": 120,
    "deletions": 15,
    "changed_files": 4,
    "created_at": "2026-04-10T12:00:00Z",
    "updated_at": "2026-04-11T12:00:00Z",
    "merged_at": None,
    "user": {"login": "contributor"},
}


def _response(payload: object) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.headers = {}
    resp.raise_for_status.return_value = None
    resp.json.return_value = payload
    return resp


def test_config_parsing_and_helpers(monkeypatch) -> None:
    monkeypatch.setenv("ALT_GITHUB_TOKEN", "env-token")
    adapter = GitHubPullRequestsAdapter(
        config={
            "queries": [" agent ", "agent", "", 42],
            "repositories": [" example/tool ", "example/tool"],
            "labels": [" bug ", "bug"],
            "state": "closed",
            "min_comments": "2",
            "max_age_days": "14",
            "token_env": "ALT_GITHUB_TOKEN",
        }
    )

    assert adapter.queries == ["agent"]
    assert adapter.repositories == ["example/tool"]
    assert adapter.labels == ["bug"]
    assert adapter.state == "closed"
    assert adapter.min_comments == 2
    assert adapter.max_age_days == 14
    assert adapter.token == "env-token"
    assert _pr_query("agent", "open") == "agent is:pr is:open"
    assert _pr_query("agent is:pr is:closed", "open") == "agent is:pr is:closed"
    assert isinstance(_parse_dt("2026-04-11T12:00:00Z"), datetime)
    assert _parse_dt("not a date") is None


def test_build_tags_extracts_labels_and_keywords() -> None:
    tags = _build_tags(
        "example/mcp-python",
        ["enhancement"],
        "Agent SDK support",
        "MCP and LLM support for Python",
    )
    assert "pull-request" in tags
    assert "enhancement" in tags
    assert "agent" in tags
    assert "llm" in tags
    assert "mcp" in tags
    assert "python" in tags


@pytest.mark.asyncio
async def test_fetch_repository_mode_converts_pull_request_signal() -> None:
    adapter = GitHubPullRequestsAdapter(config={"repositories": ["example/tool"], "queries": []})
    requests: list[dict] = []

    async def mock_get(url: str, **kwargs) -> MagicMock:
        requests.append({"url": url, **kwargs})
        return _response([MOCK_PULL])

    with patch("max.sources.github_pull_requests.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=10)

    assert requests[0]["url"] == "https://api.github.com/repos/example/tool/pulls"
    assert requests[0]["params"]["state"] == "open"
    assert len(signals) == 1

    signal = signals[0]
    assert signal.id == "github_pull_requests:example/tool#42"
    assert signal.source_type == SignalSourceType.FORUM
    assert signal.source_adapter == "github_pull_requests"
    assert signal.title == "Fix MCP agent integration failure"
    assert "broken LLM agent workflow" in signal.content
    assert signal.url == "https://github.com/example/tool/pull/42"
    assert signal.author == "contributor"
    assert signal.published_at is not None
    assert signal.metadata["repository"] == "example/tool"
    assert signal.metadata["number"] == 42
    assert signal.metadata["comments"] == 8
    assert signal.metadata["additions"] == 120
    assert signal.metadata["deletions"] == 15
    assert signal.metadata["signal_role"] == "problem"


@pytest.mark.asyncio
async def test_fetch_search_query_mode_constrains_to_pull_requests() -> None:
    adapter = GitHubPullRequestsAdapter(config={"repositories": [], "queries": ["mcp server"]})
    requests: list[dict] = []

    async def mock_get(url: str, **kwargs) -> MagicMock:
        requests.append({"url": url, **kwargs})
        return _response({"items": [{**MOCK_PULL, "pull_request": {"url": "api-pr-url"}}]})

    with patch("max.sources.github_pull_requests.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=10)

    assert requests[0]["url"] == "https://api.github.com/search/issues"
    assert requests[0]["params"]["q"] == "mcp server is:pr is:open"
    assert len(signals) == 1
    assert signals[0].metadata["search_query"] == "mcp server"


@pytest.mark.asyncio
async def test_fetch_applies_labels_min_comments_and_age_filters() -> None:
    adapter = GitHubPullRequestsAdapter(
        config={
            "repositories": ["example/tool"],
            "queries": [],
            "labels": ["bug"],
            "min_comments": 2,
            "max_age_days": 7,
        }
    )
    low_comments = {**MOCK_PULL, "number": 43, "html_url": "https://github.com/example/tool/pull/43", "comments": 1}
    wrong_label = {
        **MOCK_PULL,
        "number": 44,
        "html_url": "https://github.com/example/tool/pull/44",
        "labels": [{"name": "docs"}],
    }
    stale = {
        **MOCK_PULL,
        "number": 45,
        "html_url": "https://github.com/example/tool/pull/45",
        "updated_at": "2026-03-01T12:00:00Z",
    }

    async def mock_get(url: str, **kwargs) -> MagicMock:
        return _response([low_comments, wrong_label, stale, MOCK_PULL])

    with patch("max.sources.github_pull_requests._cutoff") as mock_cutoff, \
         patch("max.sources.github_pull_requests.httpx.AsyncClient") as mock_cls:
        mock_cutoff.return_value = datetime(2026, 4, 9, tzinfo=timezone.utc)
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].metadata["number"] == 42


@pytest.mark.asyncio
async def test_fetch_resolves_configured_and_environment_tokens(monkeypatch) -> None:
    adapter = GitHubPullRequestsAdapter(
        config={"repositories": ["example/tool"], "queries": [], "github_token": "configured-token"}
    )

    async def mock_get(url: str, **kwargs) -> MagicMock:
        return _response([])

    with patch("max.sources.github_pull_requests.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        await adapter.fetch(limit=10)

    headers = mock_cls.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer configured-token"

    monkeypatch.setenv("CUSTOM_GITHUB_TOKEN", "env-token")
    adapter = GitHubPullRequestsAdapter(
        config={"repositories": ["example/tool"], "queries": [], "token_env": "CUSTOM_GITHUB_TOKEN"}
    )
    with patch("max.sources.github_pull_requests.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        await adapter.fetch(limit=10)

    headers = mock_cls.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer env-token"


@pytest.mark.asyncio
async def test_fetch_supports_unauthenticated_requests(monkeypatch) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    adapter = GitHubPullRequestsAdapter(config={"repositories": ["example/tool"], "queries": []})

    async def mock_get(url: str, **kwargs) -> MagicMock:
        return _response([])

    with patch("max.sources.github_pull_requests.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        await adapter.fetch(limit=10)

    headers = mock_cls.call_args.kwargs["headers"]
    assert "Authorization" not in headers
