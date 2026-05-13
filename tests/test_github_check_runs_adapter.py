"""Tests for GitHub check runs import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.github_check_runs_adapter import GitHubCheckRunsAdapter


RUN = {
    "id": 123,
    "name": "CI",
    "status": "completed",
    "conclusion": "failure",
    "html_url": "https://github.com/example/tool/runs/123",
    "details_url": "https://github.example/checks/123",
    "head_sha": "abc123",
    "started_at": "2026-05-01T10:00:00Z",
    "completed_at": "2026-05-01T10:06:30Z",
    "app": {"id": 1, "slug": "github-actions", "name": "GitHub Actions"},
    "output": {"title": "Tests failed", "summary": "One test failed"},
}


@pytest.mark.asyncio
async def test_github_check_runs_fetch_filters_paginates_and_maps() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json={"check_runs": [RUN]})
        return httpx.Response(200, json={"check_runs": [{**RUN, "id": 124, "conclusion": "success"}]})

    adapter = GitHubCheckRunsAdapter(
        token="github_token",
        api_url="https://api.github.test",
        config={
            "repositories": ["example/tool"],
            "refs": ["main"],
            "status": "completed",
            "conclusion": "failure",
            "check_name": "CI",
            "per_page": 1,
        },
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert len(requests) == 2
    assert requests[0].url.path == "/repos/example/tool/commits/main/check-runs"
    assert requests[0].url.params["status"] == "completed"
    assert requests[0].url.params["filter"] == "failure"
    assert requests[0].url.params["check_name"] == "CI"
    assert requests[0].headers["Authorization"] == "Bearer github_token"
    assert requests[0].headers["Accept"] == "application/vnd.github+json"
    assert requests[0].headers["X-GitHub-Api-Version"] == "2022-11-28"
    assert [signal.metadata["check_run_id"] for signal in signals] == [123, 124]
    assert signals[0].id == "github-check-run:example/tool:main:123"
    assert signals[0].source_adapter == "github_check_runs_import"
    assert signals[0].source_type.value == "failure_data"
    assert signals[0].metadata["repository"] == "example/tool"
    assert signals[0].metadata["ref"] == "main"
    assert signals[0].metadata["name"] == "CI"
    assert signals[0].metadata["conclusion"] == "failure"
    assert signals[0].metadata["app"]["slug"] == "github-actions"
    assert signals[0].metadata["output"]["summary"] == "One test failed"


@pytest.mark.asyncio
async def test_github_check_runs_accepts_explicit_check_targets() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"check_runs": [RUN]})

    adapter = GitHubCheckRunsAdapter(
        token="github_token",
        config={"check_targets": [{"repo": "example/tool", "sha": "abc123"}]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert requests[0].url.path == "/repos/example/tool/commits/abc123/check-runs"
    assert signals[0].metadata["ref"] == "abc123"


@pytest.mark.asyncio
async def test_github_check_runs_empty_without_token_target_or_on_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    assert await GitHubCheckRunsAdapter(config={"repositories": ["example/tool"], "refs": ["main"]}).fetch() == []
    assert await GitHubCheckRunsAdapter(token="token").fetch() == []

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401)

    adapter = GitHubCheckRunsAdapter(
        token="bad",
        config={"repositories": ["example/tool"], "refs": ["main"]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    assert await adapter.fetch() == []
