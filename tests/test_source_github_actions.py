"""Tests for GitHub Actions source adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from max.sources.errors import (
    SourceAuthError,
    SourceParseError,
    SourceRateLimitError,
    SourceTransientError,
)
from max.sources.github_actions import GitHubActionsAdapter, _build_tags, _parse_dt
from max.types.signal import SignalSourceType


MOCK_RUN = {
    "id": 123456,
    "name": "CI",
    "run_number": 42,
    "status": "completed",
    "conclusion": "failure",
    "html_url": "https://github.com/example/tool/actions/runs/123456",
    "head_branch": "main",
    "head_sha": "abc123def456",
    "event": "push",
    "created_at": "2026-04-10T12:00:00Z",
    "updated_at": "2026-04-10T12:10:00Z",
    "run_started_at": "2026-04-10T12:01:00Z",
    "actor": {"login": "contributor"},
}


def _response(payload: object, *, status_code: int = 200, headers: dict | None = None) -> MagicMock:
    request = httpx.Request("GET", "https://api.github.com/test")
    response = httpx.Response(status_code, json=payload, headers=headers or {}, request=request)
    resp = MagicMock()
    resp.status_code = status_code
    resp.headers = response.headers
    resp.json.side_effect = response.json
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            f"HTTP {status_code}",
            request=request,
            response=response,
        )
    else:
        resp.raise_for_status.return_value = None
    return resp


def test_config_parsing_and_helpers(monkeypatch) -> None:
    monkeypatch.setenv("ALT_GITHUB_TOKEN", "env-token")
    adapter = GitHubActionsAdapter(
        config={
            "repositories": [" example/tool ", "example/tool", "", 42],
            "workflow_names": [" CI ", "CI"],
            "statuses": ["completed", "in_progress"],
            "conclusions": ["failure", "cancelled"],
            "max_age_days": "14",
            "token_env": "ALT_GITHUB_TOKEN",
        }
    )

    assert adapter.repositories == ["example/tool"]
    assert adapter.workflow_names == ["CI"]
    assert adapter.statuses == ["completed", "in_progress"]
    assert adapter.conclusions == ["failure", "cancelled"]
    assert adapter.max_age_days == 14
    assert adapter.token == "env-token"
    assert isinstance(_parse_dt("2026-04-10T12:00:00Z"), datetime)
    assert _parse_dt("not a date") is None


def test_build_tags_extracts_runtime_and_failure_keywords() -> None:
    tags = _build_tags("example/python-tool", "CI", "failure", "main", "push")
    assert "actions" in tags
    assert "failure" in tags
    assert "python" in tags
    assert "test" in tags


@pytest.mark.asyncio
async def test_fetch_normalizes_failed_workflow_runs() -> None:
    adapter = GitHubActionsAdapter(config={"repositories": ["example/tool"]})
    requests: list[dict] = []

    async def mock_get(url: str, **kwargs) -> MagicMock:
        requests.append({"url": url, **kwargs})
        return _response({"workflow_runs": [MOCK_RUN]})

    with patch("max.sources.github_actions.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=10)

    assert requests[0]["url"] == "https://api.github.com/repos/example/tool/actions/runs"
    assert requests[0]["params"]["status"] == "completed"
    assert len(signals) == 1

    signal = signals[0]
    assert signal.id == "github_actions:123456"
    assert signal.source_type == SignalSourceType.FAILURE_DATA
    assert signal.source_adapter == "github_actions"
    assert signal.title == "example/tool CI #42 failure"
    assert signal.url == "https://github.com/example/tool/actions/runs/123456"
    assert signal.author == "contributor"
    assert signal.published_at is not None
    assert signal.metadata["repo"] == "example/tool"
    assert signal.metadata["workflow_name"] == "CI"
    assert signal.metadata["run_id"] == 123456
    assert signal.metadata["run_number"] == 42
    assert signal.metadata["conclusion"] == "failure"
    assert signal.metadata["branch"] == "main"
    assert signal.metadata["commit_sha"] == "abc123def456"
    assert signal.metadata["event"] == "push"
    assert signal.metadata["signal_role"] == "problem"


@pytest.mark.asyncio
async def test_fetch_paginates_and_deduplicates_by_run_url() -> None:
    adapter = GitHubActionsAdapter(config={"repositories": ["example/tool"]})
    requests: list[dict] = []
    second_run = {
        **MOCK_RUN,
        "id": 999,
        "run_number": 43,
        "html_url": "https://github.com/example/tool/actions/runs/999",
    }

    async def mock_get(url: str, **kwargs) -> MagicMock:
        requests.append({"url": url, **kwargs})
        if kwargs["params"]["page"] == 1:
            return _response(
                {"workflow_runs": [MOCK_RUN, MOCK_RUN]},
                headers={"Link": '<https://api.github.com/page/2>; rel="next"'},
            )
        return _response({"workflow_runs": [second_run]})

    with patch("max.sources.github_actions.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=10)

    assert [request["params"]["page"] for request in requests] == [1, 2]
    assert [signal.url for signal in signals] == [
        "https://github.com/example/tool/actions/runs/123456",
        "https://github.com/example/tool/actions/runs/999",
    ]


@pytest.mark.asyncio
async def test_fetch_applies_workflow_conclusion_status_and_age_filters() -> None:
    adapter = GitHubActionsAdapter(
        config={
            "repositories": ["example/tool"],
            "workflow_names": ["CI"],
            "statuses": ["completed", "failure"],
            "conclusions": ["failure"],
            "max_age_days": 7,
        }
    )
    cancelled = {**MOCK_RUN, "id": 1, "html_url": "https://github.com/example/tool/actions/runs/1", "conclusion": "cancelled"}
    wrong_workflow = {**MOCK_RUN, "id": 2, "html_url": "https://github.com/example/tool/actions/runs/2", "name": "Deploy"}
    stale = {
        **MOCK_RUN,
        "id": 3,
        "html_url": "https://github.com/example/tool/actions/runs/3",
        "updated_at": "2026-03-01T12:00:00Z",
    }
    requests: list[dict] = []

    async def mock_get(url: str, **kwargs) -> MagicMock:
        requests.append({"url": url, **kwargs})
        return _response({"workflow_runs": [cancelled, wrong_workflow, stale, MOCK_RUN]})

    with patch("max.sources.github_actions._cutoff") as mock_cutoff, \
         patch("max.sources.github_actions.httpx.AsyncClient") as mock_cls:
        mock_cutoff.return_value = datetime(2026, 4, 9, tzinfo=timezone.utc)
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=10)

    assert [request["params"]["status"] for request in requests] == ["completed", "failure"]
    assert all(request["params"]["created"] == ">=2026-04-09" for request in requests)
    assert len(signals) == 1
    assert signals[0].metadata["run_id"] == 123456


@pytest.mark.asyncio
async def test_fetch_resolves_configured_and_environment_tokens(monkeypatch) -> None:
    adapter = GitHubActionsAdapter(
        config={"repositories": ["example/tool"], "github_token": "configured-token"}
    )

    async def mock_get(url: str, **kwargs) -> MagicMock:
        return _response({"workflow_runs": []})

    with patch("max.sources.github_actions.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        await adapter.fetch(limit=10)

    headers = mock_cls.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer configured-token"

    monkeypatch.setenv("CUSTOM_GITHUB_TOKEN", "env-token")
    adapter = GitHubActionsAdapter(
        config={"repositories": ["example/tool"], "token_env": "CUSTOM_GITHUB_TOKEN"}
    )
    with patch("max.sources.github_actions.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        await adapter.fetch(limit=10)

    headers = mock_cls.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer env-token"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "headers", "expected_error"),
    [
        (401, {}, SourceAuthError),
        (403, {}, SourceAuthError),
        (429, {"Retry-After": "0"}, SourceRateLimitError),
        (500, {}, SourceTransientError),
    ],
)
async def test_fetch_maps_http_errors(status_code, headers, expected_error) -> None:
    adapter = GitHubActionsAdapter(config={"repositories": ["example/tool"]})

    async def mock_get(url: str, **kwargs) -> MagicMock:
        return _response({"message": "error"}, status_code=status_code, headers=headers)

    with patch("max.sources.retry.asyncio.sleep", new_callable=AsyncMock), \
         patch("max.sources.github_actions.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        with pytest.raises(expected_error):
            await adapter.fetch(limit=10)


@pytest.mark.asyncio
async def test_fetch_maps_malformed_response_to_parse_error() -> None:
    adapter = GitHubActionsAdapter(config={"repositories": ["example/tool"]})

    async def mock_get(url: str, **kwargs) -> MagicMock:
        return _response({"not_workflow_runs": []})

    with patch("max.sources.github_actions.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        with pytest.raises(SourceParseError):
            await adapter.fetch(limit=10)
