"""Tests for the GitLab releases source adapter."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from max.sources.gitlab_releases import (
    GitLabReleasesAdapter,
    _encode_project,
    _parse_dt,
    _releases_url,
)
from max.types.signal import SignalSourceType


MOCK_RELEASE = {
    "name": "Agent SDK 1.0",
    "tag_name": "v1.0.0",
    "description": "Release notes with AI agent workflow improvements.",
    "released_at": "2026-04-15T10:30:00.000Z",
    "created_at": "2026-04-14T09:00:00.000Z",
    "project_id": 278964,
    "_links": {"self": "https://gitlab.com/example/tool/-/releases/v1.0.0"},
    "commit": {
        "id": "abc123",
        "web_url": "https://gitlab.com/example/tool/-/commit/abc123",
    },
    "milestones": [{"title": "1.0"}],
    "assets": {"links": [{"name": "binary"}], "sources": [{"format": "zip"}]},
}


def _response(payload: object) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = payload
    return resp


def test_project_path_encoding_handles_plain_and_encoded_paths() -> None:
    assert _encode_project("278964") == "278964"
    assert _encode_project("group/subgroup/project") == "group%2Fsubgroup%2Fproject"
    assert _encode_project("group%2Fsubgroup%2Fproject") == "group%2Fsubgroup%2Fproject"
    assert (
        _releases_url("https://gitlab.example.com", "group/project")
        == "https://gitlab.example.com/api/v4/projects/group%2Fproject/releases"
    )
    assert (
        _releases_url("https://gitlab.example.com/api/v4", "group/project")
        == "https://gitlab.example.com/api/v4/projects/group%2Fproject/releases"
    )


def test_parse_dt_valid_and_invalid_values() -> None:
    dt = _parse_dt("2026-04-15T10:30:00.000Z")
    assert isinstance(dt, datetime)
    assert dt.tzinfo is not None
    assert _parse_dt("not-a-date") is None
    assert _parse_dt(None) is None


@pytest.mark.asyncio
async def test_gitlab_releases_fetch_success_normalizes_signal() -> None:
    adapter = GitLabReleasesAdapter(config={"projects": ["example/tool"]})

    async def mock_fetch_with_retry(url: str, client, *, adapter_name: str, params: dict):
        assert url == "https://gitlab.com/api/v4/projects/example%2Ftool/releases"
        assert adapter_name == "gitlab_releases"
        assert params == {"per_page": 10, "page": 1}
        return _response([MOCK_RELEASE])

    with patch("max.sources.gitlab_releases.fetch_with_retry", mock_fetch_with_retry):
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    signal = signals[0]
    assert signal.source_type == SignalSourceType.REGISTRY
    assert signal.source_adapter == "gitlab_releases"
    assert signal.title == "example/tool Agent SDK 1.0 (v1.0.0)"
    assert "AI agent workflow" in signal.content
    assert signal.url == "https://gitlab.com/example/tool/-/releases/v1.0.0"
    assert signal.published_at is not None
    assert "gitlab" in signal.tags
    assert "release" in signal.tags
    assert signal.metadata["project_id"] == 278964
    assert signal.metadata["project_path"] == "example/tool"
    assert signal.metadata["tag_name"] == "v1.0.0"
    assert signal.metadata["commit_path"] == "https://gitlab.com/example/tool/-/commit/abc123"
    assert signal.metadata["milestones"] == ["1.0"]
    assert signal.metadata["assets_count"] == 2
    assert signal.metadata["evidence_tags"] == signal.tags


@pytest.mark.asyncio
async def test_gitlab_releases_paginates_until_limit() -> None:
    adapter = GitLabReleasesAdapter(config={"projects": ["example/tool"]})
    requested_pages: list[int] = []
    second_release = {
        **MOCK_RELEASE,
        "name": "Agent SDK 1.1",
        "tag_name": "v1.1.0",
        "_links": {"self": "https://gitlab.com/example/tool/-/releases/v1.1.0"},
    }
    prerelease = {
        **MOCK_RELEASE,
        "tag_name": "v2.0.0-rc1",
        "prerelease": True,
        "_links": {"self": "https://gitlab.com/example/tool/-/releases/v2.0.0-rc1"},
    }
    responses = [
        _response([MOCK_RELEASE, prerelease]),
        _response([second_release]),
    ]

    async def mock_fetch_with_retry(url: str, client, *, adapter_name: str, params: dict):
        requested_pages.append(params["page"])
        return responses.pop(0)

    with patch("max.sources.gitlab_releases.fetch_with_retry", mock_fetch_with_retry):
        signals = await adapter.fetch(limit=2)

    assert requested_pages == [1, 2]
    assert [signal.metadata["tag_name"] for signal in signals] == ["v1.0.0", "v1.1.0"]


@pytest.mark.asyncio
async def test_gitlab_releases_uses_configured_token_env_header(monkeypatch) -> None:
    monkeypatch.setenv("CUSTOM_GITLAB_TOKEN", "secret-token")
    adapter = GitLabReleasesAdapter(
        config={"projects": ["example/tool"], "token_env": "CUSTOM_GITLAB_TOKEN"}
    )

    async def mock_fetch_with_retry(url: str, client, *, adapter_name: str, params: dict):
        return _response([])

    with patch("max.sources.gitlab_releases.fetch_with_retry", mock_fetch_with_retry), \
         patch("max.sources.gitlab_releases.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        await adapter.fetch(limit=10)

    headers = mock_cls.call_args.kwargs["headers"]
    assert headers["Accept"] == "application/json"
    assert headers["PRIVATE-TOKEN"] == "secret-token"


@pytest.mark.asyncio
async def test_gitlab_releases_supports_unauthenticated_requests(monkeypatch) -> None:
    monkeypatch.delenv("GITLAB_TOKEN", raising=False)
    adapter = GitLabReleasesAdapter(config={"projects": ["example/tool"]})

    async def mock_fetch_with_retry(url: str, client, *, adapter_name: str, params: dict):
        return _response([])

    with patch("max.sources.gitlab_releases.fetch_with_retry", mock_fetch_with_retry), \
         patch("max.sources.gitlab_releases.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        await adapter.fetch(limit=10)

    assert "PRIVATE-TOKEN" not in mock_cls.call_args.kwargs["headers"]


@pytest.mark.asyncio
async def test_gitlab_releases_filters_by_max_age_tags_and_query_terms() -> None:
    adapter = GitLabReleasesAdapter(
        config={
            "projects": ["example/tool"],
            "max_age_days": 365,
            "tags": ["agent"],
            "query_terms": ["workflow"],
        }
    )
    old_release = {
        **MOCK_RELEASE,
        "released_at": "2000-01-01T00:00:00Z",
        "_links": {"self": "https://gitlab.com/example/tool/-/releases/old"},
    }
    unmatched_release = {
        **MOCK_RELEASE,
        "description": "Maintenance release.",
        "tag_name": "v1.0.1",
        "_links": {"self": "https://gitlab.com/example/tool/-/releases/v1.0.1"},
    }

    async def mock_fetch_with_retry(url: str, client, *, adapter_name: str, params: dict):
        return _response([old_release, unmatched_release, MOCK_RELEASE])

    with patch("max.sources.gitlab_releases.fetch_with_retry", mock_fetch_with_retry):
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].metadata["tag_name"] == "v1.0.0"


@pytest.mark.asyncio
async def test_gitlab_releases_handles_malformed_release_payloads() -> None:
    adapter = GitLabReleasesAdapter(config={"projects": ["example/tool"]})
    missing_url = {**MOCK_RELEASE, "_links": {}, "url": "", "web_url": ""}
    missing_name = {
        **MOCK_RELEASE,
        "name": "",
        "tag_name": "",
        "_links": {"self": "https://gitlab.com/example/tool/-/releases/missing-name"},
    }

    async def mock_fetch_with_retry(url: str, client, *, adapter_name: str, params: dict):
        return _response(["not-a-dict", missing_url, missing_name, MOCK_RELEASE])

    with patch("max.sources.gitlab_releases.fetch_with_retry", mock_fetch_with_retry):
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].metadata["tag_name"] == "v1.0.0"


@pytest.mark.asyncio
async def test_gitlab_releases_handles_non_list_response() -> None:
    adapter = GitLabReleasesAdapter(config={"projects": ["example/tool"]})

    async def mock_fetch_with_retry(url: str, client, *, adapter_name: str, params: dict):
        return _response({"message": "bad payload"})

    with patch("max.sources.gitlab_releases.fetch_with_retry", mock_fetch_with_retry):
        signals = await adapter.fetch(limit=10)

    assert signals == []
