"""Tests for the GitLab Merge Requests source adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from max.sources.gitlab_merge_requests import (
    GitLabMergeRequestsAdapter,
    _build_tags,
    _merge_requests_url,
    _parse_dt,
)
from max.types.signal import SignalSourceType


MOCK_MERGE_REQUEST = {
    "id": 7001,
    "iid": 17,
    "project_id": 278964,
    "title": "Fix MCP agent integration failure",
    "description": "The implementation fixes a broken LLM agent workflow.",
    "web_url": "https://gitlab.com/example/ai-toolkit/-/merge_requests/17",
    "references": {"full": "example/ai-toolkit!17"},
    "state": "opened",
    "author": {"username": "contributor", "name": "Contributor"},
    "created_at": "2026-04-15T10:30:00.000Z",
    "updated_at": "2026-04-16T11:00:00.000Z",
    "labels": ["bug", "integration"],
    "upvotes": 12,
    "user_notes_count": 8,
}

MOCK_SECOND_MERGE_REQUEST = {
    "id": 7002,
    "iid": 18,
    "project_id": 278965,
    "title": "Add Python SDK support",
    "description": "Adds project support for agent workflows.",
    "web_url": "https://gitlab.com/group/subgroup/sdk/-/merge_requests/18",
    "state": "merged",
    "author": {"username": "maintainer"},
    "created_at": "2026-04-10T09:00:00.000Z",
    "updated_at": "2026-04-11T09:00:00.000Z",
    "labels": ["enhancement"],
    "upvotes": 3,
    "comments_count": 4,
}


def _response(payload: object) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.headers = {}
    resp.raise_for_status.return_value = None
    resp.json.return_value = payload
    return resp


def test_config_parsing_and_helpers(monkeypatch) -> None:
    monkeypatch.setenv("ALT_GITLAB_TOKEN", "env-token")
    adapter = GitLabMergeRequestsAdapter(
        config={
            "project_ids": [278964, " group/project ", "group/project", None],
            "queries": [" agent ", "agent", "", 42],
            "labels": [" bug ", "bug"],
            "state": "merged",
            "min_upvotes": "2",
            "max_age_days": "14",
            "gitlab_base_url": "https://gitlab.example.com/api/v4/",
            "token_env": "ALT_GITLAB_TOKEN",
        }
    )

    assert adapter.project_ids == ["278964", "group/project"]
    assert adapter.queries == ["agent", "42"]
    assert adapter.labels == ["bug"]
    assert adapter.state == "merged"
    assert adapter.min_upvotes == 2
    assert adapter.max_age_days == 14
    assert adapter.gitlab_base_url == "https://gitlab.example.com/api/v4"
    assert adapter.token == "env-token"
    assert _merge_requests_url("https://gitlab.com/api/v4", None) == (
        "https://gitlab.com/api/v4/merge_requests"
    )
    assert _merge_requests_url("https://gitlab.com/api/v4", "group/project") == (
        "https://gitlab.com/api/v4/projects/group%2Fproject/merge_requests"
    )
    assert isinstance(_parse_dt("2026-04-15T10:30:00.000Z"), datetime)
    assert _parse_dt("not-a-date") is None


def test_build_tags_extracts_labels_and_keywords() -> None:
    tags = _build_tags(
        "example/mcp-python",
        ["enhancement"],
        "Agent SDK support",
        "MCP and LLM support for Python",
    )
    assert "merge-request" in tags
    assert "enhancement" in tags
    assert "agent" in tags
    assert "llm" in tags
    assert "mcp" in tags
    assert "python" in tags


@pytest.mark.asyncio
async def test_fetch_project_mode_converts_merge_request_signal() -> None:
    adapter = GitLabMergeRequestsAdapter(config={"project_ids": ["example/ai-toolkit"], "queries": []})
    requests: list[dict] = []

    async def mock_get(url: str, **kwargs) -> MagicMock:
        requests.append({"url": url, **kwargs})
        return _response([MOCK_MERGE_REQUEST])

    with patch("max.sources.gitlab_merge_requests.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=10)

    assert requests[0]["url"] == (
        "https://gitlab.com/api/v4/projects/example%2Fai-toolkit/merge_requests"
    )
    assert requests[0]["params"]["state"] == "opened"
    assert requests[0]["params"]["order_by"] == "updated_at"
    assert len(signals) == 1

    signal = signals[0]
    assert signal.id == "gitlab_merge_requests:example/ai-toolkit!17"
    assert signal.source_type == SignalSourceType.FORUM
    assert signal.source_adapter == "gitlab_merge_requests"
    assert signal.title == "Fix MCP agent integration failure"
    assert "broken LLM agent workflow" in signal.content
    assert signal.url == "https://gitlab.com/example/ai-toolkit/-/merge_requests/17"
    assert signal.author == "contributor"
    assert signal.published_at is not None
    assert signal.credibility == 0.55
    assert signal.metadata["project_id"] == 278964
    assert signal.metadata["project_path"] == "example/ai-toolkit"
    assert signal.metadata["merge_request_iid"] == 17
    assert signal.metadata["state"] == "opened"
    assert signal.metadata["labels"] == ["bug", "integration"]
    assert signal.metadata["author"] == "contributor"
    assert signal.metadata["upvotes"] == 12
    assert signal.metadata["comments_count"] == 8
    assert signal.metadata["created_at"] == "2026-04-15T10:30:00.000Z"
    assert signal.metadata["updated_at"] == "2026-04-16T11:00:00.000Z"
    assert signal.metadata["url"] == signal.url
    assert signal.metadata["project_id_config"] == "example/ai-toolkit"


@pytest.mark.asyncio
async def test_fetch_query_mode_uses_global_merge_requests_search() -> None:
    adapter = GitLabMergeRequestsAdapter(config={"project_ids": [], "queries": ["mcp server"]})
    requests: list[dict] = []

    async def mock_get(url: str, **kwargs) -> MagicMock:
        requests.append({"url": url, **kwargs})
        return _response([MOCK_SECOND_MERGE_REQUEST])

    with patch("max.sources.gitlab_merge_requests.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=10)

    assert requests[0]["url"] == "https://gitlab.com/api/v4/merge_requests"
    assert requests[0]["params"]["search"] == "mcp server"
    assert requests[0]["params"]["scope"] == "all"
    assert len(signals) == 1
    assert signals[0].metadata["search_query"] == "mcp server"
    assert signals[0].metadata["project_path"] == "group/subgroup/sdk"


@pytest.mark.asyncio
async def test_fetch_applies_labels_state_min_upvotes_age_and_token(monkeypatch) -> None:
    monkeypatch.setenv("CUSTOM_GITLAB_TOKEN", "secret-token")
    adapter = GitLabMergeRequestsAdapter(
        config={
            "project_ids": ["278964"],
            "queries": [],
            "labels": ["bug"],
            "state": "merged",
            "min_upvotes": 10,
            "max_age_days": 7,
            "token_env": "CUSTOM_GITLAB_TOKEN",
        }
    )
    low_upvotes = {
        **MOCK_MERGE_REQUEST,
        "id": 7003,
        "iid": 19,
        "web_url": "https://gitlab.com/example/ai-toolkit/-/merge_requests/19",
        "upvotes": 1,
    }
    wrong_label = {
        **MOCK_MERGE_REQUEST,
        "id": 7004,
        "iid": 20,
        "web_url": "https://gitlab.com/example/ai-toolkit/-/merge_requests/20",
        "labels": ["docs"],
    }
    stale = {
        **MOCK_MERGE_REQUEST,
        "id": 7005,
        "iid": 21,
        "web_url": "https://gitlab.com/example/ai-toolkit/-/merge_requests/21",
        "updated_at": "2026-03-01T12:00:00Z",
    }
    requests: list[dict] = []

    async def mock_get(url: str, **kwargs) -> MagicMock:
        requests.append({"url": url, **kwargs})
        return _response([low_upvotes, wrong_label, stale, MOCK_MERGE_REQUEST])

    with patch("max.sources.gitlab_merge_requests._cutoff") as mock_cutoff, \
         patch("max.sources.gitlab_merge_requests.httpx.AsyncClient") as mock_cls:
        mock_cutoff.return_value = datetime(2026, 4, 9, tzinfo=timezone.utc)
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=10)

    headers = mock_cls.call_args.kwargs["headers"]
    assert headers["PRIVATE-TOKEN"] == "secret-token"
    assert requests[0]["params"]["state"] == "merged"
    assert requests[0]["params"]["labels"] == "bug"
    assert len(signals) == 1
    assert signals[0].metadata["merge_request_iid"] == 17


@pytest.mark.asyncio
async def test_fetch_deduplicates_urls_and_respects_limit() -> None:
    adapter = GitLabMergeRequestsAdapter(config={"project_ids": [], "queries": ["agent", "llm"]})

    async def mock_get(url: str, **kwargs) -> MagicMock:
        return _response([MOCK_MERGE_REQUEST, MOCK_MERGE_REQUEST])

    with patch("max.sources.gitlab_merge_requests.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=1)

    assert len(signals) == 1
    assert signals[0].url == MOCK_MERGE_REQUEST["web_url"]
