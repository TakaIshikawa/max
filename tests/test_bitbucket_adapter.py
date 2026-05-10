"""Tests for Bitbucket import adapter — repository signal collection."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from max.imports.bitbucket_adapter import (
    BitbucketAdapter,
    _build_tags,
    _parse_dt,
)
from max.types.signal import SignalSourceType


# ── Test Data ────────────────────────────────────────────────────────

MOCK_REPO = {
    "full_name": "atlassian/python-bitbucket",
    "description": "Python wrapper for the Bitbucket API",
    "language": "python",
    "links": {"html": {"href": "https://bitbucket.org/atlassian/python-bitbucket"}},
    "owner": {"display_name": "Atlassian"},
    "created_on": "2023-06-15T10:00:00+00:00",
    "updated_on": "2024-01-20T08:00:00+00:00",
    "has_wiki": True,
    "has_issues": True,
    "fork_policy": "allow_forks",
    "scm": "git",
    "is_private": False,
}

MOCK_REPO_2 = {
    "full_name": "atlassian/adf-builder-python",
    "description": "ADF builder for Python",
    "language": "python",
    "links": {"html": {"href": "https://bitbucket.org/atlassian/adf-builder-python"}},
    "owner": {"display_name": "Atlassian"},
    "created_on": "2023-08-10T12:00:00+00:00",
    "updated_on": "2024-01-18T06:00:00+00:00",
    "has_wiki": False,
    "has_issues": True,
    "fork_policy": "no_public_forks",
    "scm": "git",
    "is_private": False,
}

MOCK_WORKSPACE_RESPONSE = {"values": [MOCK_REPO, MOCK_REPO_2], "page": 1, "size": 2}
MOCK_SEARCH_RESPONSE = {"values": [MOCK_REPO], "page": 1, "size": 1}
MOCK_EMPTY_RESPONSE = {"values": [], "page": 1, "size": 0}


def _mock_response(payload: dict, *, status_code: int = 200) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.json.return_value = payload
    resp.status_code = status_code
    resp.raise_for_status.return_value = None
    return resp


# ── Unit tests ───────────────────────────────────────────────────────


def test_parse_dt_valid() -> None:
    dt = _parse_dt("2024-01-15T10:00:00+00:00")
    assert dt is not None
    assert dt.year == 2024


def test_parse_dt_zulu() -> None:
    dt = _parse_dt("2024-01-15T10:00:00Z")
    assert dt is not None


def test_parse_dt_none() -> None:
    assert _parse_dt(None) is None


def test_build_tags_python() -> None:
    tags = _build_tags("python", "atlassian")
    assert "bitbucket" in tags
    assert "python" in tags
    assert "atlassian" in tags


def test_build_tags_no_language() -> None:
    tags = _build_tags(None, "myworkspace")
    assert "bitbucket" in tags
    assert "myworkspace" in tags


# ── Adapter property tests ───────────────────────────────────────────


def test_adapter_name() -> None:
    adapter = BitbucketAdapter()
    assert adapter.name == "bitbucket_import"


def test_adapter_source_type() -> None:
    adapter = BitbucketAdapter()
    assert adapter.source_type == SignalSourceType.TRENDING.value


def test_adapter_default_workspaces() -> None:
    adapter = BitbucketAdapter()
    assert "atlassian" in adapter.workspaces


def test_adapter_custom_workspaces() -> None:
    adapter = BitbucketAdapter(config={"workspaces": ["myorg"]})
    assert adapter.workspaces == ["myorg"]


def test_adapter_query() -> None:
    adapter = BitbucketAdapter(config={"query": "mcp"})
    assert adapter.query == "mcp"


def test_adapter_language() -> None:
    adapter = BitbucketAdapter(config={"language": "python"})
    assert adapter.language == "python"


# ── Fetch tests with mocked API ──────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_workspace_repos() -> None:
    adapter = BitbucketAdapter(config={"workspaces": ["atlassian"]})

    with patch(
        "max.imports.bitbucket_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch, patch(
        "max.imports.bitbucket_adapter._get_credentials",
        return_value=(None, None),
    ):
        mock_fetch.return_value = _mock_response(MOCK_WORKSPACE_RESPONSE)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 2
    sig = signals[0]
    assert sig.title == "atlassian/python-bitbucket"
    assert sig.source_adapter == "bitbucket_import"
    assert sig.source_type == SignalSourceType.TRENDING
    assert sig.url == "https://bitbucket.org/atlassian/python-bitbucket"
    assert sig.author == "Atlassian"
    assert sig.metadata["language"] == "python"
    assert sig.metadata["has_wiki"] is True
    assert sig.metadata["scm"] == "git"


@pytest.mark.asyncio
async def test_fetch_search_repos() -> None:
    adapter = BitbucketAdapter(config={"query": "python-bitbucket"})

    with patch(
        "max.imports.bitbucket_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch, patch(
        "max.imports.bitbucket_adapter._get_credentials",
        return_value=(None, None),
    ):
        mock_fetch.return_value = _mock_response(MOCK_SEARCH_RESPONSE)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].title == "atlassian/python-bitbucket"


@pytest.mark.asyncio
async def test_fetch_respects_limit() -> None:
    adapter = BitbucketAdapter(config={"workspaces": ["atlassian"]})

    with patch(
        "max.imports.bitbucket_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch, patch(
        "max.imports.bitbucket_adapter._get_credentials",
        return_value=(None, None),
    ):
        mock_fetch.return_value = _mock_response(MOCK_WORKSPACE_RESPONSE)
        signals = await adapter.fetch(limit=1)

    assert len(signals) == 1


@pytest.mark.asyncio
async def test_fetch_deduplicates() -> None:
    dup_response = {"values": [MOCK_REPO, MOCK_REPO], "page": 1, "size": 2}
    adapter = BitbucketAdapter(config={"workspaces": ["atlassian"]})

    with patch(
        "max.imports.bitbucket_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch, patch(
        "max.imports.bitbucket_adapter._get_credentials",
        return_value=(None, None),
    ):
        mock_fetch.return_value = _mock_response(dup_response)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1


@pytest.mark.asyncio
async def test_fetch_handles_api_error() -> None:
    adapter = BitbucketAdapter(config={"workspaces": ["atlassian"]})

    with patch(
        "max.imports.bitbucket_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch, patch(
        "max.imports.bitbucket_adapter._get_credentials",
        return_value=(None, None),
    ):
        mock_fetch.side_effect = Exception("API error")
        signals = await adapter.fetch(limit=10)

    assert signals == []


@pytest.mark.asyncio
async def test_fetch_empty_response() -> None:
    adapter = BitbucketAdapter(config={"workspaces": ["atlassian"]})

    with patch(
        "max.imports.bitbucket_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch, patch(
        "max.imports.bitbucket_adapter._get_credentials",
        return_value=(None, None),
    ):
        mock_fetch.return_value = _mock_response(MOCK_EMPTY_RESPONSE)
        signals = await adapter.fetch(limit=10)

    assert signals == []


@pytest.mark.asyncio
async def test_fetch_with_auth() -> None:
    adapter = BitbucketAdapter(config={"workspaces": ["atlassian"]})

    with patch(
        "max.imports.bitbucket_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch, patch(
        "max.imports.bitbucket_adapter._get_credentials",
        return_value=("user", "pass"),
    ):
        mock_fetch.return_value = _mock_response(MOCK_WORKSPACE_RESPONSE)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 2
