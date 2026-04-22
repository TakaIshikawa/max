"""Tests for the GitLab Issues source adapter."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from max.sources.gitlab_issues import (
    GitLabIssuesAdapter,
    _build_tags,
    _issues_url,
    _parse_dt,
)
from max.types.signal import SignalSourceType


MOCK_GITLAB_ISSUE_1 = {
    "id": 5001,
    "iid": 101,
    "project_id": 278964,
    "title": "AI agent workflow is slow",
    "description": "Running multi-step agent workflows creates high latency.",
    "web_url": "https://gitlab.com/example/ai-toolkit/-/issues/101",
    "state": "opened",
    "author": {"username": "dev1", "name": "Developer One"},
    "created_at": "2026-04-15T10:30:00.000Z",
    "labels": ["performance", "ai"],
    "upvotes": 12,
    "user_notes_count": 8,
}

MOCK_GITLAB_ISSUE_2 = {
    "id": 5002,
    "iid": 202,
    "project_id": 278965,
    "title": "LLM integration bug",
    "description": "Provider requests fail with large prompts.",
    "web_url": "https://gitlab.com/example/llm-lib/-/issues/202",
    "state": "opened",
    "author": {"username": "dev2"},
    "created_at": "2026-04-14T09:00:00.000Z",
    "labels": ["bug"],
    "upvotes": 3,
    "comments_count": 4,
}


def test_issues_url_for_global_and_project_scoped_requests() -> None:
    assert _issues_url(None) == "https://gitlab.com/api/v4/issues"
    assert _issues_url("278964") == "https://gitlab.com/api/v4/projects/278964/issues"
    assert (
        _issues_url("group/subgroup/project")
        == "https://gitlab.com/api/v4/projects/group%2Fsubgroup%2Fproject/issues"
    )


def test_parse_dt_valid_and_invalid_values() -> None:
    dt = _parse_dt("2026-04-15T10:30:00.000Z")
    assert isinstance(dt, datetime)
    assert dt.tzinfo is not None

    assert _parse_dt("not-a-date") is None
    assert _parse_dt(None) is None


def test_build_tags_includes_labels_keywords_and_gitlab() -> None:
    tags = _build_tags(["Performance", "bug"], "AI Agent LLM vulnerability")
    assert "performance" in tags
    assert "bug" in tags
    assert "ai" in tags
    assert "agent" in tags
    assert "llm" in tags
    assert "security" in tags
    assert "gitlab" in tags


@pytest.mark.asyncio
async def test_gitlab_issues_adapter_fetch_success() -> None:
    adapter = GitLabIssuesAdapter(config={"queries": ["agent"], "labels": ["bug", "ai"]})
    requested_params: list[dict] = []

    async def mock_get(url: str, **kwargs) -> MagicMock:
        requested_params.append(kwargs["params"])
        return MagicMock(
            json=lambda: [MOCK_GITLAB_ISSUE_1, MOCK_GITLAB_ISSUE_2],
            raise_for_status=lambda: None,
        )

    with patch("max.sources.gitlab_issues.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 2
    assert requested_params[0]["search"] == "agent"
    assert requested_params[0]["labels"] == "bug,ai"
    assert requested_params[0]["state"] == "opened"

    first = signals[0]
    assert first.source_type == SignalSourceType.FORUM
    assert first.source_adapter == "gitlab_issues"
    assert first.title == "AI agent workflow is slow"
    assert first.author == "dev1"
    assert first.published_at is not None
    assert first.credibility == (12 + 8) / 100
    assert first.metadata["project_id"] == 278964
    assert first.metadata["issue_iid"] == 101
    assert first.metadata["labels"] == ["performance", "ai"]
    assert first.metadata["upvotes"] == 12
    assert first.metadata["comments_count"] == 8
    assert first.metadata["search_query"] == "agent"


@pytest.mark.asyncio
async def test_gitlab_issues_adapter_uses_project_ids_state_min_upvotes_and_token() -> None:
    adapter = GitLabIssuesAdapter(
        config={
            "queries": ["llm"],
            "project_ids": [278964, "group/project"],
            "state": "closed",
            "min_upvotes": 10,
        }
    )
    requested_urls: list[str] = []
    requested_params: list[dict] = []

    async def mock_get(url: str, **kwargs) -> MagicMock:
        requested_urls.append(url)
        requested_params.append(kwargs["params"])
        return MagicMock(
            json=lambda: [MOCK_GITLAB_ISSUE_1, MOCK_GITLAB_ISSUE_2],
            raise_for_status=lambda: None,
        )

    with patch.dict("os.environ", {"GITLAB_TOKEN": "secret"}, clear=False), \
         patch("max.sources.gitlab_issues.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=10)

    assert mock_cls.call_args.kwargs["headers"]["PRIVATE-TOKEN"] == "secret"
    assert requested_urls == [
        "https://gitlab.com/api/v4/projects/278964/issues",
        "https://gitlab.com/api/v4/projects/group%2Fproject/issues",
    ]
    assert all(params["state"] == "closed" for params in requested_params)
    assert [signal.metadata["upvotes"] for signal in signals] == [12]


@pytest.mark.asyncio
async def test_gitlab_issues_adapter_deduplicates_urls_and_respects_limit() -> None:
    adapter = GitLabIssuesAdapter(config={"queries": ["agent", "llm"]})

    async def mock_get(url: str, **kwargs) -> MagicMock:
        return MagicMock(
            json=lambda: [MOCK_GITLAB_ISSUE_1, MOCK_GITLAB_ISSUE_1],
            raise_for_status=lambda: None,
        )

    with patch("max.sources.gitlab_issues.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=1)

    assert len(signals) == 1
    assert signals[0].url == MOCK_GITLAB_ISSUE_1["web_url"]
