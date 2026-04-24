"""Tests for Bitbucket Pull Requests source adapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from max.sources.bitbucket_pull_requests import (
    BitbucketPullRequestsAdapter,
    _build_tags,
    _parse_dt,
)
from max.sources.registry import get_adapter, list_adapters, reload_registry
from max.types.signal import SignalSourceType


MOCK_PULL = {
    "id": 42,
    "title": "Fix MCP agent integration failure",
    "description": "This fixes a broken LLM agent workflow and adds safer retries.",
    "state": "OPEN",
    "comment_count": 8,
    "task_count": 3,
    "created_on": "2026-04-10T12:00:00+00:00",
    "updated_on": "2026-04-11T12:00:00+00:00",
    "author": {"nickname": "contributor", "display_name": "Contributor"},
    "links": {"html": {"href": "https://bitbucket.org/example/tool/pull-requests/42"}},
}


def _response(payload: object) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.headers = {}
    resp.json.return_value = payload
    return resp


def test_config_parsing_and_helpers(monkeypatch) -> None:
    monkeypatch.setenv("ALT_BITBUCKET_TOKEN", "env-token")
    adapter = BitbucketPullRequestsAdapter(
        config={
            "repositories": [" example/tool ", "example/tool", ""],
            "workspace": "acme",
            "repository": "platform",
            "repository_slugs": ["api", "api"],
            "states": ["open", "MERGED", "invalid"],
            "query": 'title ~ "agent"',
            "token_env": "ALT_BITBUCKET_TOKEN",
        }
    )

    assert adapter.repositories == ["example/tool", "acme/platform", "acme/api"]
    assert adapter.states == ["OPEN", "MERGED"]
    assert adapter.query == 'title ~ "agent"'
    assert adapter.token == "env-token"
    assert _parse_dt("2026-04-11T12:00:00Z") is not None
    assert _parse_dt("not a date") is None


def test_build_tags_extracts_state_and_keywords() -> None:
    tags = _build_tags(
        "example/mcp-python",
        "Agent SDK support",
        "MCP and LLM support for Python",
        "MERGED",
    )

    assert "bitbucket" in tags
    assert "pull-request" in tags
    assert "merged" in tags
    assert "agent" in tags
    assert "llm" in tags
    assert "mcp" in tags
    assert "python" in tags


@pytest.mark.asyncio
async def test_fetch_public_repository_converts_pull_request_signal() -> None:
    adapter = BitbucketPullRequestsAdapter(config={"repositories": ["example/tool"]})
    requests: list[dict] = []

    async def mock_fetch(url: str, client, *, adapter_name: str, params=None):
        requests.append({"url": url, "adapter_name": adapter_name, "params": params})
        return _response({"values": [MOCK_PULL]})

    with patch("max.sources.bitbucket_pull_requests.fetch_with_retry", mock_fetch), \
         patch("max.sources.bitbucket_pull_requests.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=10)

    assert requests[0]["url"] == (
        "https://api.bitbucket.org/2.0/repositories/example/tool/pullrequests"
    )
    assert requests[0]["adapter_name"] == "bitbucket_pull_requests"
    assert requests[0]["params"]["state"] == ["OPEN", "MERGED", "DECLINED"]
    assert len(signals) == 1

    signal = signals[0]
    assert signal.id == "bitbucket_pull_requests:example/tool#42"
    assert signal.source_type == SignalSourceType.FORUM
    assert signal.source_adapter == "bitbucket_pull_requests"
    assert signal.title == "Fix MCP agent integration failure"
    assert "broken LLM agent workflow" in signal.content
    assert signal.url == "https://bitbucket.org/example/tool/pull-requests/42"
    assert signal.author == "contributor"
    assert signal.metadata["repository"] == "example/tool"
    assert signal.metadata["bitbucket_pull_request_id"] == 42
    assert signal.metadata["state"] == "OPEN"
    assert signal.metadata["comment_count"] == 8
    assert signal.metadata["task_count"] == 3
    assert signal.metadata["signal_role"] == "problem"


@pytest.mark.asyncio
async def test_fetch_sends_token_only_in_authorization_header() -> None:
    adapter = BitbucketPullRequestsAdapter(
        config={"repositories": ["example/tool"], "bitbucket_token": "configured-token"}
    )

    async def mock_fetch(url: str, client, *, adapter_name: str, params=None):
        return _response({"values": [MOCK_PULL]})

    with patch("max.sources.bitbucket_pull_requests.fetch_with_retry", mock_fetch), \
         patch("max.sources.bitbucket_pull_requests.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=10)

    headers = mock_cls.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer configured-token"
    assert "configured-token" not in str(signals[0].metadata)


@pytest.mark.asyncio
async def test_fetch_supports_unauthenticated_requests(monkeypatch) -> None:
    monkeypatch.delenv("BITBUCKET_TOKEN", raising=False)
    adapter = BitbucketPullRequestsAdapter(config={"repositories": ["example/tool"]})

    async def mock_fetch(url: str, client, *, adapter_name: str, params=None):
        return _response({"values": []})

    with patch("max.sources.bitbucket_pull_requests.fetch_with_retry", mock_fetch), \
         patch("max.sources.bitbucket_pull_requests.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        await adapter.fetch(limit=10)

    headers = mock_cls.call_args.kwargs["headers"]
    assert "Authorization" not in headers


@pytest.mark.asyncio
async def test_fetch_applies_state_query_pagination_and_limit() -> None:
    adapter = BitbucketPullRequestsAdapter(
        config={
            "repositories": ["example/tool"],
            "state": "merged",
            "query": 'title ~ "agent"',
        }
    )
    page_two_pull = {
        **MOCK_PULL,
        "id": 43,
        "state": "MERGED",
        "links": {"html": {"href": "https://bitbucket.org/example/tool/pull-requests/43"}},
    }
    requests: list[dict] = []

    async def mock_fetch(url: str, client, *, adapter_name: str, params=None):
        requests.append({"url": url, "params": params})
        if len(requests) == 1:
            return _response(
                {
                    "values": [MOCK_PULL],
                    "next": "https://api.bitbucket.org/2.0/repositories/example/tool/pullrequests?page=2",
                }
            )
        return _response({"values": [page_two_pull]})

    with patch("max.sources.bitbucket_pull_requests.fetch_with_retry", mock_fetch), \
         patch("max.sources.bitbucket_pull_requests.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=2)
        limited_signals = await adapter.fetch(limit=1)

    assert len(signals) == 2
    assert len(requests) == 3
    assert requests[0]["params"] == {
        "pagelen": 2,
        "sort": "-updated_on",
        "state": ["MERGED"],
        "q": 'title ~ "agent"',
    }
    assert requests[1]["params"] is None
    assert requests[1]["url"].endswith("page=2")
    assert requests[2]["params"]["pagelen"] == 1
    assert len(limited_signals) == 1


def test_registry_includes_bitbucket_pull_requests() -> None:
    reload_registry()
    try:
        assert "bitbucket_pull_requests" in list_adapters()
        adapter = get_adapter("bitbucket_pull_requests")
        assert isinstance(adapter, BitbucketPullRequestsAdapter)
    finally:
        reload_registry()
