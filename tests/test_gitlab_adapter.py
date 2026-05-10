"""Tests for GitLab import adapter — repository signal collection."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from max.imports.gitlab_adapter import (
    GitLabAdapter,
    _build_tags,
    _parse_dt,
)
from max.types.signal import SignalSourceType


# ── Test Data ────────────────────────────────────────────────────────

MOCK_PROJECT = {
    "id": 1001,
    "path_with_namespace": "org/ai-toolkit",
    "description": "AI development toolkit with MCP support",
    "web_url": "https://gitlab.com/org/ai-toolkit",
    "star_count": 500,
    "forks_count": 80,
    "open_issues_count": 12,
    "topics": ["ai-agent", "llm", "python"],
    "created_at": "2025-01-15T10:00:00Z",
    "last_activity_at": "2026-05-08T14:00:00Z",
    "visibility": "public",
    "default_branch": "main",
    "namespace": {"name": "org"},
}

MOCK_PROJECT_2 = {
    "id": 1002,
    "path_with_namespace": "devtools/mcp-server",
    "description": "MCP server for GitLab CI",
    "web_url": "https://gitlab.com/devtools/mcp-server",
    "star_count": 200,
    "forks_count": 30,
    "open_issues_count": 5,
    "topics": ["mcp", "devops"],
    "created_at": "2025-06-01T12:00:00Z",
    "last_activity_at": "2026-05-07T09:00:00Z",
    "visibility": "public",
    "default_branch": "main",
    "namespace": {"name": "devtools"},
}

MOCK_PROJECTS_RESPONSE = [MOCK_PROJECT, MOCK_PROJECT_2]


def _mock_response(payload, *, status_code: int = 200) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.json.return_value = payload
    resp.status_code = status_code
    resp.raise_for_status.return_value = None
    resp.text = str(payload)
    return resp


# ── Unit tests ───────────────────────────────────────────────────────


def test_parse_dt_valid() -> None:
    dt = _parse_dt("2026-05-08T14:00:00Z")
    assert isinstance(dt, datetime)
    assert dt.year == 2026


def test_parse_dt_none() -> None:
    assert _parse_dt(None) is None


def test_parse_dt_invalid() -> None:
    assert _parse_dt("bad") is None


def test_build_tags_basic() -> None:
    tags = _build_tags(["ai-agent", "llm"], "mcp")
    assert "agent" in tags
    assert "ai" in tags
    assert "mcp" in tags
    assert "gitlab" in tags


def test_build_tags_empty() -> None:
    tags = _build_tags([], "custom")
    assert "custom" in tags
    assert "gitlab" in tags


# ── Adapter property tests ───────────────────────────────────────────


def test_adapter_name() -> None:
    adapter = GitLabAdapter()
    assert adapter.name == "gitlab_import"


def test_adapter_source_type() -> None:
    adapter = GitLabAdapter()
    assert adapter.source_type == SignalSourceType.TRENDING.value


def test_adapter_default_topics() -> None:
    adapter = GitLabAdapter()
    assert "mcp" in adapter.topics


def test_adapter_custom_topics() -> None:
    adapter = GitLabAdapter(config={"topics": ["devops", "ci-cd"]})
    assert adapter.topics == ["devops", "ci-cd"]


def test_adapter_default_base_url() -> None:
    adapter = GitLabAdapter()
    assert adapter.base_url == "https://gitlab.com/api/v4"


def test_adapter_custom_base_url() -> None:
    adapter = GitLabAdapter(config={"base_url": "https://gitlab.internal.co/api/v4"})
    assert adapter.base_url == "https://gitlab.internal.co/api/v4"


def test_adapter_group_id() -> None:
    adapter = GitLabAdapter(config={"group_id": "12345"})
    assert adapter.group_id == "12345"


def test_adapter_group_id_default() -> None:
    adapter = GitLabAdapter()
    assert adapter.group_id is None


# ── Fetch tests with mocked API ─────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_parses_projects() -> None:
    adapter = GitLabAdapter(config={"topics": ["mcp"]})

    with patch(
        "max.imports.gitlab_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.return_value = _mock_response(MOCK_PROJECTS_RESPONSE)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 2
    sig = signals[0]
    assert sig.title == "org/ai-toolkit"
    assert sig.source_adapter == "gitlab_import"
    assert sig.source_type == SignalSourceType.TRENDING
    assert sig.url == "https://gitlab.com/org/ai-toolkit"
    assert sig.author == "org"
    assert sig.metadata["stars"] == 500
    assert sig.metadata["forks"] == 80
    assert sig.metadata["open_issues_count"] == 12
    assert sig.metadata["visibility"] == "public"
    assert sig.published_at is not None


@pytest.mark.asyncio
async def test_fetch_respects_limit() -> None:
    adapter = GitLabAdapter(config={"topics": ["mcp"]})

    with patch(
        "max.imports.gitlab_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.return_value = _mock_response(MOCK_PROJECTS_RESPONSE)
        signals = await adapter.fetch(limit=1)

    assert len(signals) == 1


@pytest.mark.asyncio
async def test_fetch_deduplicates() -> None:
    dup_response = [MOCK_PROJECT, MOCK_PROJECT]
    adapter = GitLabAdapter(config={"topics": ["mcp"]})

    with patch(
        "max.imports.gitlab_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.return_value = _mock_response(dup_response)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1


@pytest.mark.asyncio
async def test_fetch_handles_api_error() -> None:
    adapter = GitLabAdapter(config={"topics": ["mcp"]})

    with patch(
        "max.imports.gitlab_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.side_effect = Exception("API error")
        signals = await adapter.fetch(limit=10)

    assert signals == []


@pytest.mark.asyncio
async def test_fetch_self_hosted() -> None:
    adapter = GitLabAdapter(config={
        "topics": ["mcp"],
        "base_url": "https://gitlab.internal.co/api/v4",
    })

    with patch(
        "max.imports.gitlab_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.return_value = _mock_response(MOCK_PROJECTS_RESPONSE)
        await adapter.fetch(limit=10)

    call_url = mock_fetch.call_args[0][0]
    assert call_url.startswith("https://gitlab.internal.co/api/v4")


@pytest.mark.asyncio
async def test_fetch_with_group_id() -> None:
    adapter = GitLabAdapter(config={
        "topics": ["mcp"],
        "group_id": "42",
    })

    with patch(
        "max.imports.gitlab_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.return_value = _mock_response(MOCK_PROJECTS_RESPONSE)
        await adapter.fetch(limit=10)

    call_url = mock_fetch.call_args[0][0]
    assert "/groups/42/projects" in call_url


@pytest.mark.asyncio
async def test_fetch_non_list_response_skipped() -> None:
    adapter = GitLabAdapter(config={"topics": ["mcp"]})

    with patch(
        "max.imports.gitlab_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.return_value = _mock_response({"error": "not found"})
        signals = await adapter.fetch(limit=10)

    assert signals == []


@pytest.mark.asyncio
async def test_fetch_missing_description_uses_path() -> None:
    no_desc = {**MOCK_PROJECT, "description": None}
    adapter = GitLabAdapter(config={"topics": ["mcp"]})

    with patch(
        "max.imports.gitlab_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.return_value = _mock_response([no_desc])
        signals = await adapter.fetch(limit=10)

    assert signals[0].content == "org/ai-toolkit"
