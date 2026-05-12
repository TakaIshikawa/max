"""Tests for Bitbucket pull request import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.bitbucket_pull_requests_adapter import BitbucketPullRequestsAdapter


PR = {
    "id": 7,
    "title": "Add audit export",
    "description": "Export audit details for enterprise customers.",
    "state": "OPEN",
    "links": {"html": {"href": "https://bitbucket.org/example/tool/pull-requests/7"}},
    "author": {"display_name": "Ada", "nickname": "ada"},
    "source": {"branch": {"name": "feature/audit-export"}},
    "destination": {"branch": {"name": "main"}},
    "comment_count": 4,
    "task_count": 2,
    "created_on": "2026-05-01T10:00:00+00:00",
    "updated_on": "2026-05-02T10:00:00+00:00",
}


@pytest.mark.asyncio
async def test_bitbucket_pull_requests_fetch_follows_next_and_maps() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                200,
                json={
                    "values": [PR],
                    "next": "https://api.bitbucket.test/2.0/repositories/example/tool/pullrequests?page=2",
                },
            )
        return httpx.Response(200, json={"values": [{**PR, "id": 8, "title": "Second"}]})

    adapter = BitbucketPullRequestsAdapter(
        token="bb_token",
        api_url="https://api.bitbucket.test/2.0",
        config={
            "workspaces": ["example"],
            "repositories": ["tool"],
            "state": "OPEN",
            "pagelen": 1,
        },
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert len(requests) == 2
    assert requests[0].headers["Authorization"] == "Bearer bb_token"
    assert requests[0].url.path == "/2.0/repositories/example/tool/pullrequests"
    assert requests[0].url.params["state"] == "OPEN"
    assert [signal.metadata["pull_request_id"] for signal in signals] == [7, 8]
    assert signals[0].source_adapter == "bitbucket_pull_requests_import"
    assert signals[0].metadata["workspace"] == "example"
    assert signals[0].metadata["repository"] == "tool"
    assert signals[0].metadata["source_branch"] == "feature/audit-export"
    assert signals[0].metadata["destination_branch"] == "main"
    assert signals[0].metadata["comment_count"] == 4
    assert signals[0].metadata["task_count"] == 2


@pytest.mark.asyncio
async def test_bitbucket_pull_requests_empty_without_auth_config_or_on_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("BITBUCKET_USERNAME", raising=False)
    monkeypatch.delenv("BITBUCKET_APP_PASSWORD", raising=False)
    monkeypatch.delenv("BITBUCKET_TOKEN", raising=False)

    assert (
        await BitbucketPullRequestsAdapter(
            config={"workspaces": ["example"], "repositories": ["tool"]}
        ).fetch()
        == []
    )
    assert await BitbucketPullRequestsAdapter(token="token", config={"workspaces": ["example"]}).fetch() == []

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    adapter = BitbucketPullRequestsAdapter(
        token="bad",
        config={"workspaces": ["example"], "repositories": ["tool"]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    assert await adapter.fetch() == []
