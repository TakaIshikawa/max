"""Tests for GitLab issues import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.gitlab_issues_adapter import (
    GitLabIssuesAdapter,
    GitLabIssuesImportAdapter,
)


def _issue(number: int, *, iid: int | None = None) -> dict:
    return {
        "id": 1000 + number,
        "iid": iid or number,
        "project_id": 278964,
        "title": f"Issue {number}",
        "description": f"Customer asks for workflow {number}",
        "state": "opened",
        "labels": ["customer", "roadmap"],
        "web_url": f"https://gitlab.example/group/tool/-/issues/{number}",
        "created_at": "2026-05-01T10:00:00.000Z",
        "updated_at": "2026-05-02T10:00:00.000Z",
        "closed_at": None,
        "milestone": {"id": 7, "iid": 1, "title": "v1", "state": "active", "web_url": "https://milestone"},
        "assignees": [{"id": 4, "username": "dev", "name": "Developer", "web_url": "https://dev"}],
        "author": {"id": 5, "username": "author", "name": "Author", "web_url": "https://author"},
    }


@pytest.mark.asyncio
async def test_gitlab_issues_fetches_encoded_project_paths_and_maps_signal() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[_issue(1)])

    adapter = GitLabIssuesImportAdapter(
        token="gitlab-token",
        api_url="https://gitlab.example/api/v4",
        config={"projects": ["group/sub/tool"], "per_page": 5},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert GitLabIssuesAdapter is GitLabIssuesImportAdapter
    assert len(requests) == 1
    assert requests[0].headers["PRIVATE-TOKEN"] == "gitlab-token"
    assert str(requests[0].url).startswith(
        "https://gitlab.example/api/v4/projects/group%2Fsub%2Ftool/issues"
    )
    assert requests[0].url.params["page"] == "1"
    assert requests[0].url.params["per_page"] == "1"

    signal = signals[0]
    assert signal.id == "gitlab-issue:group/sub/tool:1"
    assert signal.source_adapter == "gitlab_issues_import"
    assert signal.source_type.value == "roadmap"
    assert signal.title == "Issue 1"
    assert signal.content == "Customer asks for workflow 1"
    assert signal.url == "https://gitlab.example/group/tool/-/issues/1"
    assert signal.author == "author"
    assert signal.published_at is not None
    assert signal.metadata["signal_role"] == "readiness"
    assert signal.metadata["project_id"] == 278964
    assert signal.metadata["project_path"] == "group/sub/tool"
    assert signal.metadata["issue_iid"] == 1
    assert signal.metadata["issue_id"] == 1001
    assert signal.metadata["state"] == "opened"
    assert signal.metadata["labels"] == ["customer", "roadmap"]
    assert signal.metadata["milestone"]["title"] == "v1"
    assert signal.metadata["assignees"][0]["username"] == "dev"
    assert signal.metadata["author"]["username"] == "author"
    assert signal.metadata["created_at"] == "2026-05-01T10:00:00.000Z"
    assert signal.metadata["updated_at"] == "2026-05-02T10:00:00.000Z"
    assert signal.metadata["closed_at"] is None
    assert signal.metadata["raw"]["id"] == 1001
    assert {"gitlab", "issue", "opened", "customer"} <= set(signal.tags)


@pytest.mark.asyncio
async def test_gitlab_issues_paginates_across_projects_with_limits() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        raw_path = request.url.raw_path.decode().split("?", 1)[0]
        if raw_path.endswith("/group%2Ftool/issues") and request.url.params["page"] == "1":
            return httpx.Response(200, json=[_issue(1)])
        if raw_path.endswith("/group%2Ftool/issues") and request.url.params["page"] == "2":
            return httpx.Response(200, json=[_issue(2)])
        return httpx.Response(200, json=[_issue(3)])

    adapter = GitLabIssuesImportAdapter(
        token="gitlab-token",
        api_url="https://gitlab.example",
        config={"project_paths": ["group/tool", "278964"], "per_page": 1, "per_project_limit": 2},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=3)

    assert [request.url.params["page"] for request in requests] == ["1", "2", "1"]
    assert requests[2].url.path == "/api/v4/projects/278964/issues"
    assert [signal.metadata["issue_iid"] for signal in signals] == [1, 2, 3]


@pytest.mark.asyncio
async def test_gitlab_issues_sends_filters_and_env_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITLAB_PRIVATE_TOKEN", "private-token")
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[_issue(1)])

    adapter = GitLabIssuesImportAdapter(
        config={
            "project_ids": "group/tool",
            "base_url": "https://gitlab.example",
            "state": "closed",
            "labels": "customer,bug",
            "milestone": "v1",
            "created_after": "2026-05-01T00:00:00Z",
            "created_before": "2026-05-31T00:00:00Z",
            "updated_after": "2026-05-02T00:00:00Z",
            "updated_before": "2026-05-30T00:00:00Z",
            "order_by": "updated_at",
            "sort": "asc",
        },
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    await adapter.fetch(limit=1)

    assert requests[0].headers["PRIVATE-TOKEN"] == "private-token"
    assert requests[0].url.params["state"] == "closed"
    assert requests[0].url.params["labels"] == "customer,bug"
    assert requests[0].url.params["milestone"] == "v1"
    assert requests[0].url.params["created_after"] == "2026-05-01T00:00:00Z"
    assert requests[0].url.params["created_before"] == "2026-05-31T00:00:00Z"
    assert requests[0].url.params["updated_after"] == "2026-05-02T00:00:00Z"
    assert requests[0].url.params["updated_before"] == "2026-05-30T00:00:00Z"
    assert requests[0].url.params["order_by"] == "updated_at"
    assert requests[0].url.params["sort"] == "asc"


@pytest.mark.asyncio
async def test_gitlab_issues_empty_without_required_config_or_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITLAB_PRIVATE_TOKEN", raising=False)
    monkeypatch.delenv("GITLAB_TOKEN", raising=False)

    assert await GitLabIssuesImportAdapter(config={"projects": ["group/tool"]}).fetch() == []
    assert await GitLabIssuesImportAdapter(token="token").fetch() == []
    assert await GitLabIssuesImportAdapter(token="token", config={"projects": ["group/tool"]}).fetch(limit=0) == []


@pytest.mark.asyncio
async def test_gitlab_issues_http_or_non_json_failure_returns_empty() -> None:
    failing = GitLabIssuesImportAdapter(
        token="gitlab-token",
        config={"projects": ["group/tool"]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500))),
    )
    assert await failing.fetch(limit=2) == []

    non_json = GitLabIssuesImportAdapter(
        token="gitlab-token",
        config={"projects": ["group/tool"]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, text="nope"))),
    )
    assert await non_json.fetch(limit=2) == []
