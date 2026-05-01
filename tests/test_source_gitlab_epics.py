"""Tests for the GitLab Epics source adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from max.sources.errors import SourceAuthError
from max.sources.gitlab_epics import (
    GitLabEpicsAdapter,
    _build_tags,
    _epics_url,
    _parse_dt,
)
from max.types.signal import SignalSourceType


MOCK_EPIC = {
    "id": 9001,
    "iid": 42,
    "title": "Enterprise AI agent roadmap",
    "description": "Plan SSO and MCP support for enterprise LLM agent workflows.",
    "web_url": "https://gitlab.com/example/platform/-/epics/42",
    "references": {"full": "example/platform&42"},
    "state": "opened",
    "author": {"username": "planner", "name": "Planner"},
    "created_at": "2026-04-15T10:30:00.000Z",
    "updated_at": "2026-04-16T11:00:00.000Z",
    "labels": ["roadmap", "enterprise"],
    "upvotes": 15,
    "downvotes": 2,
    "user_notes_count": 7,
}

MOCK_SECOND_EPIC = {
    "id": 9002,
    "iid": 43,
    "title": "Improve security planning",
    "description": "Track compliance work for customer deployments.",
    "web_url": "https://gitlab.com/group/subgroup/-/epics/43",
    "state": "closed",
    "author": {"username": "pm"},
    "created_at": "2026-04-10T09:00:00.000Z",
    "updated_at": "2026-04-11T09:00:00.000Z",
    "labels": [{"name": "security"}],
    "upvotes": 3,
    "comments_count": 4,
}


def _response(payload: object, *, next_page: str = "") -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.headers = {"X-Next-Page": next_page}
    resp.raise_for_status.return_value = None
    resp.json.return_value = payload
    return resp


def test_config_parsing_and_helpers(monkeypatch) -> None:
    monkeypatch.setenv("GITLAB_TOKEN", "env-token")
    adapter = GitLabEpicsAdapter(
        config={
            "groups": [123, " example/platform ", "example/platform", None],
            "labels": [" roadmap ", "roadmap", 42],
            "state": "closed",
            "gitlab_url": "https://gitlab.example.com/api/v4/",
            "per_group_limit": "12",
            "timeout": "9.5",
            "max_age_days": "30",
        }
    )

    assert adapter.name == "gitlab_epics"
    assert adapter.source_type == "roadmap"
    assert adapter.groups == ["123", "example/platform"]
    assert adapter.labels == ["roadmap", "42"]
    assert adapter.state == "closed"
    assert adapter.gitlab_url == "https://gitlab.example.com/api/v4"
    assert adapter.private_token == "env-token"
    assert adapter.per_group_limit == 12
    assert adapter.timeout == 9.5
    assert adapter.max_age_days == 30
    assert _epics_url("https://gitlab.com/api/v4", "group/subgroup") == (
        "https://gitlab.com/api/v4/groups/group%2Fsubgroup/epics"
    )
    assert isinstance(_parse_dt("2026-04-15T10:30:00.000Z"), datetime)
    assert _parse_dt("not-a-date") is None


def test_build_tags_extracts_planning_keywords() -> None:
    tags = _build_tags(
        "example/platform",
        ["roadmap"],
        "Enterprise Agent Strategy",
        "MCP support for LLM customers",
    )
    assert "roadmap" in tags
    assert "epic" in tags
    assert "enterprise" in tags
    assert "agent" in tags
    assert "llm" in tags
    assert "mcp" in tags


@pytest.mark.asyncio
async def test_fetch_converts_gitlab_epics_to_roadmap_signals() -> None:
    adapter = GitLabEpicsAdapter(
        config={
            "groups": ["example/platform"],
            "labels": ["roadmap"],
            "state": "all",
            "private_token": "secret-token",
            "timeout": 12,
        }
    )
    requests: list[dict] = []

    async def mock_get(url: str, **kwargs) -> MagicMock:
        requests.append({"url": url, **kwargs})
        return _response([MOCK_EPIC, MOCK_SECOND_EPIC])

    with patch("max.sources.gitlab_epics.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=10)

    assert mock_cls.call_args.kwargs["timeout"] == 12
    assert mock_cls.call_args.kwargs["headers"]["PRIVATE-TOKEN"] == "secret-token"
    assert requests[0]["url"] == (
        "https://gitlab.com/api/v4/groups/example%2Fplatform/epics"
    )
    assert requests[0]["params"]["state"] == "all"
    assert requests[0]["params"]["labels"] == "roadmap"
    assert requests[0]["params"]["order_by"] == "updated_at"
    assert len(signals) == 1

    signal = signals[0]
    assert signal.id == "gitlab_epics:example/platform&42"
    assert signal.source_type == SignalSourceType.ROADMAP
    assert signal.source_adapter == "gitlab_epics"
    assert signal.title == "Enterprise AI agent roadmap"
    assert "SSO and MCP support" in signal.content
    assert signal.url == "https://gitlab.com/example/platform/-/epics/42"
    assert signal.author == "planner"
    assert signal.published_at is not None
    assert signal.credibility == 0.6
    assert signal.metadata["gitlab_epic_id"] == 9001
    assert signal.metadata["group"] == "example/platform"
    assert signal.metadata["group_path"] == "example/platform"
    assert signal.metadata["epic_iid"] == 42
    assert signal.metadata["labels"] == ["roadmap", "enterprise"]
    assert signal.metadata["state"] == "opened"
    assert signal.metadata["web_url"] == signal.url
    assert signal.metadata["upvotes"] == 15
    assert signal.metadata["downvotes"] == 2
    assert signal.metadata["comments_count"] == 7
    assert signal.metadata["created_at"] == "2026-04-15T10:30:00.000Z"
    assert signal.metadata["updated_at"] == "2026-04-16T11:00:00.000Z"
    assert signal.metadata["signal_role"] == "market"


@pytest.mark.asyncio
async def test_fetch_deduplicates_skips_malformed_and_respects_limit() -> None:
    adapter = GitLabEpicsAdapter(config={"groups": ["example/platform", "other/group"]})
    malformed = {**MOCK_EPIC, "web_url": ""}

    async def mock_get(url: str, **kwargs) -> MagicMock:
        return _response([malformed, MOCK_EPIC, MOCK_EPIC])

    with patch("max.sources.gitlab_epics.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=1)

    assert len(signals) == 1
    assert signals[0].url == MOCK_EPIC["web_url"]


@pytest.mark.asyncio
async def test_fetch_respects_per_group_limit_and_paginates_conservatively() -> None:
    adapter = GitLabEpicsAdapter(
        config={"groups": ["example/platform"], "per_group_limit": 2, "labels": []}
    )
    requests: list[dict] = []
    page_payloads = [
        ([MOCK_EPIC], "2"),
        ([{**MOCK_SECOND_EPIC, "web_url": "https://gitlab.com/example/platform/-/epics/43"}], ""),
    ]

    async def mock_get(url: str, **kwargs) -> MagicMock:
        requests.append({"url": url, **kwargs})
        payload, next_page = page_payloads[len(requests) - 1]
        return _response(payload, next_page=next_page)

    with patch("max.sources.gitlab_epics.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 2
    assert [request["params"]["page"] for request in requests] == [1, 2]
    assert all(request["params"]["per_page"] <= 2 for request in requests)


@pytest.mark.asyncio
async def test_fetch_applies_max_age_filter() -> None:
    adapter = GitLabEpicsAdapter(config={"groups": ["example/platform"], "max_age_days": 7})
    stale = {
        **MOCK_EPIC,
        "id": 9003,
        "iid": 44,
        "web_url": "https://gitlab.com/example/platform/-/epics/44",
        "updated_at": "2026-03-01T12:00:00Z",
    }

    async def mock_get(url: str, **kwargs) -> MagicMock:
        return _response([stale, MOCK_EPIC])

    with patch("max.sources.gitlab_epics._cutoff") as mock_cutoff, \
         patch("max.sources.gitlab_epics.httpx.AsyncClient") as mock_cls:
        mock_cutoff.return_value = datetime(2026, 4, 9, tzinfo=timezone.utc)
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].metadata["epic_iid"] == 42


@pytest.mark.asyncio
async def test_auth_errors_are_raised() -> None:
    adapter = GitLabEpicsAdapter(config={"groups": ["example/platform"]})

    async def mock_get(url: str, **kwargs) -> MagicMock:
        request = httpx.Request("GET", url)
        response = httpx.Response(401, request=request)
        response.raise_for_status()
        raise AssertionError("unreachable")

    with patch("max.sources.gitlab_epics.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        with pytest.raises(SourceAuthError):
            await adapter.fetch(limit=10)


@pytest.mark.asyncio
async def test_transient_errors_follow_adapter_convention_and_skip_group() -> None:
    adapter = GitLabEpicsAdapter(config={"groups": ["example/platform"]})

    async def mock_get(url: str, **kwargs) -> MagicMock:
        request = httpx.Request("GET", url)
        response = httpx.Response(503, request=request)
        response.raise_for_status()
        raise AssertionError("unreachable")

    with patch("max.sources.retry.asyncio.sleep", new=AsyncMock()), \
         patch("max.sources.gitlab_epics.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=10)

    assert signals == []
