"""Tests for GitHub workflow runs source adapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from max.sources.errors import SourceAuthError, SourceRateLimitError
from max.sources.github_workflow_runs import GitHubWorkflowRunsAdapter
from max.types.signal import SignalSourceType


MOCK_RUN = {
    "id": 123,
    "name": "CI",
    "run_number": 17,
    "status": "completed",
    "conclusion": "failure",
    "html_url": "https://github.com/example/tool/actions/runs/123",
    "head_branch": "main",
    "head_sha": "abc123",
    "event": "push",
    "created_at": "2026-04-10T12:00:00Z",
    "run_started_at": "2026-04-10T12:02:00Z",
    "updated_at": "2026-04-10T12:17:30Z",
    "actor": {"login": "octocat"},
}


def _response(payload: object, *, status_code: int = 200, headers: dict | None = None) -> MagicMock:
    request = httpx.Request("GET", "https://api.github.test/repos/example/tool/actions/runs")
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


@pytest.mark.asyncio
async def test_fetch_normalizes_failed_workflow_runs() -> None:
    adapter = GitHubWorkflowRunsAdapter(
        config={"repositories": ["example/tool"], "api_url": "https://api.github.test"}
    )
    requests: list[dict] = []

    async def mock_get(url: str, **kwargs) -> MagicMock:
        requests.append({"url": url, **kwargs})
        return _response({"workflow_runs": [MOCK_RUN]})

    with patch("max.sources.github_workflow_runs.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=10)

    assert requests[0]["url"] == "https://api.github.test/repos/example/tool/actions/runs"
    assert requests[0]["params"] == {"status": "completed", "per_page": 30, "page": 1}
    assert mock_cls.call_args.kwargs["timeout"] == 30.0

    assert len(signals) == 1
    signal = signals[0]
    assert signal.id == "github_workflow_runs:123"
    assert signal.source_type == SignalSourceType.FAILURE_DATA
    assert signal.source_adapter == "github_workflow_runs"
    assert signal.title == "example/tool CI #17 failure (930s)"
    assert signal.url == "https://github.com/example/tool/actions/runs/123"
    assert signal.author == "octocat"
    assert "failure" in signal.tags
    assert signal.metadata["workflow_name"] == "CI"
    assert signal.metadata["repository"] == "example/tool"
    assert signal.metadata["status"] == "completed"
    assert signal.metadata["conclusion"] == "failure"
    assert signal.metadata["duration_seconds"] == 930
    assert signal.metadata["queued_seconds"] == 120
    assert signal.metadata["run_url"] == "https://github.com/example/tool/actions/runs/123"
    assert signal.metadata["signal_role"] == "problem"


@pytest.mark.asyncio
async def test_fetch_filters_by_status_conclusion_and_slow_duration() -> None:
    adapter = GitHubWorkflowRunsAdapter(
        config={
            "repositories": ["example/tool"],
            "statuses": ["completed", "in_progress"],
            "conclusions": ["timed_out"],
            "slow_run_seconds": 600,
            "timeout": 9,
        }
    )
    failed = {
        **MOCK_RUN,
        "updated_at": "2026-04-10T12:03:00Z",
    }
    timed_out = {
        **MOCK_RUN,
        "id": 124,
        "conclusion": "timed_out",
        "html_url": "https://github.com/example/tool/actions/runs/124",
    }
    slow_success = {
        **MOCK_RUN,
        "id": 125,
        "conclusion": "success",
        "html_url": "https://github.com/example/tool/actions/runs/125",
        "updated_at": "2026-04-10T12:45:00Z",
    }
    fast_success = {
        **MOCK_RUN,
        "id": 126,
        "conclusion": "success",
        "html_url": "https://github.com/example/tool/actions/runs/126",
        "updated_at": "2026-04-10T12:03:00Z",
    }
    requests: list[dict] = []

    async def mock_get(url: str, **kwargs) -> MagicMock:
        requests.append({"url": url, **kwargs})
        return _response({"workflow_runs": [failed, timed_out, slow_success, fast_success]})

    with patch("max.sources.github_workflow_runs.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=10)

    assert [request["params"]["status"] for request in requests] == ["completed", "in_progress"]
    assert mock_cls.call_args.kwargs["timeout"] == 9.0
    assert [signal.metadata["run_id"] for signal in signals] == [124, 125]
    assert "slow" in signals[1].tags


@pytest.mark.asyncio
async def test_fetch_respects_pagination_cap_and_deduplicates_by_run_url() -> None:
    adapter = GitHubWorkflowRunsAdapter(
        config={"repositories": ["example/tool"], "max_runs_per_repo": 2}
    )
    second_run = {
        **MOCK_RUN,
        "id": 999,
        "run_number": 18,
        "html_url": "https://github.com/example/tool/actions/runs/999",
    }
    requests: list[dict] = []

    async def mock_get(url: str, **kwargs) -> MagicMock:
        requests.append({"url": url, **kwargs})
        return _response(
            {"workflow_runs": [MOCK_RUN, MOCK_RUN, second_run]},
            headers={"Link": '<https://api.github.com/page/2>; rel="next"'},
        )

    with patch("max.sources.github_workflow_runs.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=10)

    assert len(requests) == 1
    assert requests[0]["params"]["per_page"] == 2
    assert [signal.url for signal in signals] == [
        "https://github.com/example/tool/actions/runs/123",
        "https://github.com/example/tool/actions/runs/999",
    ]


@pytest.mark.asyncio
async def test_fetch_tolerates_transient_api_failures() -> None:
    adapter = GitHubWorkflowRunsAdapter(config={"repositories": ["example/tool", "example/ok"]})
    requests: list[str] = []

    async def mock_get(url: str, **kwargs) -> MagicMock:
        requests.append(url)
        if "example/tool" in url:
            return _response({"message": "server error"}, status_code=500)
        return _response({"workflow_runs": [MOCK_RUN]})

    with patch("max.sources.retry.asyncio.sleep", new_callable=AsyncMock), \
         patch("max.sources.github_workflow_runs.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=10)

    assert len(requests) == 5
    assert len(signals) == 1
    assert signals[0].metadata["repository"] == "example/ok"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "headers", "expected_error"),
    [
        (401, {}, SourceAuthError),
        (403, {}, SourceAuthError),
        (429, {"Retry-After": "0"}, SourceRateLimitError),
        (403, {"X-RateLimit-Remaining": "0"}, SourceRateLimitError),
    ],
)
async def test_fetch_raises_auth_and_rate_limit_errors(status_code, headers, expected_error) -> None:
    adapter = GitHubWorkflowRunsAdapter(config={"repositories": ["example/tool"]})

    async def mock_get(url: str, **kwargs) -> MagicMock:
        return _response({"message": "error"}, status_code=status_code, headers=headers)

    with patch("max.sources.retry.asyncio.sleep", new_callable=AsyncMock), \
         patch("max.sources.github_workflow_runs.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        with pytest.raises(expected_error):
            await adapter.fetch(limit=10)


def test_config_parsing_and_token_resolution(monkeypatch) -> None:
    monkeypatch.setenv("ALT_GITHUB_TOKEN", "env-token")
    adapter = GitHubWorkflowRunsAdapter(
        config={
            "repositories": [" example/tool ", "example/tool", "", 1],
            "statuses": "completed",
            "conclusions": [" failure ", "failure", "", 3],
            "max_runs_per_repo": "12",
            "slow_run_seconds": "900",
            "token_env": "ALT_GITHUB_TOKEN",
            "api_url": "https://github.enterprise.test/api/v3/",
        }
    )

    assert adapter.repositories == ["example/tool"]
    assert adapter.statuses == ["completed"]
    assert adapter.conclusions == ["failure"]
    assert adapter.max_runs_per_repo == 12
    assert adapter.slow_run_seconds == 900
    assert adapter.token == "env-token"
    assert adapter.api_url == "https://github.enterprise.test/api/v3"
