"""Tests for GitHub issue timeline events import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.github_issue_timeline_events_adapter import GitHubIssueTimelineEventsAdapter
from max.types.signal import SignalSourceType


LABELED_EVENT = {
    "id": 1001,
    "node_id": "LE_kwDOA1",
    "url": "https://api.github.example/repos/acme/api/issues/events/1001",
    "event": "labeled",
    "actor": {
        "login": "octocat",
        "id": 1,
        "node_id": "MDQ6VXNlcjE=",
        "type": "User",
        "html_url": "https://github.example/octocat",
    },
    "created_at": "2026-05-01T10:00:00Z",
    "label": {"name": "bug", "color": "d73a4a"},
}

CROSS_REFERENCED_EVENT = {
    "id": 1002,
    "event": "cross-referenced",
    "actor": {"login": "hubot", "id": 2, "type": "Bot"},
    "created_at": "2026-05-01T11:00:00Z",
    "source": {
        "issue": {
            "title": "Related support escalation",
            "html_url": "https://github.example/acme/api/issues/7",
        }
    },
}


@pytest.mark.asyncio
async def test_github_issue_timeline_events_fetch_paginates_across_issues_and_maps() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/v3/repos/acme/api/issues/42/timeline":
            return httpx.Response(200, json=[LABELED_EVENT])
        if request.url.path == "/api/v3/repos/acme/api/issues/43/timeline":
            return httpx.Response(200, json=[CROSS_REFERENCED_EVENT])
        return httpx.Response(404)

    adapter = GitHubIssueTimelineEventsAdapter(
        token="gh-token",
        api_url="https://github.example/api/v3",
        config={
            "repository": "acme/api",
            "issue_numbers": [42, 43],
            "per_page": 2,
            "since": "2026-05-01T00:00:00Z",
        },
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert len(requests) == 2
    assert requests[0].url.path == "/api/v3/repos/acme/api/issues/42/timeline"
    assert requests[0].url.params["per_page"] == "2"
    assert requests[0].url.params["page"] == "1"
    assert requests[0].url.params["since"] == "2026-05-01T00:00:00Z"
    assert requests[1].url.path == "/api/v3/repos/acme/api/issues/43/timeline"
    assert requests[0].headers["Authorization"] == "Bearer gh-token"

    signal = signals[0]
    assert signal.id == "github-issue-timeline-event:acme/api:42:1001"
    assert signal.source_type == SignalSourceType.ROADMAP
    assert signal.source_adapter == "github_issue_timeline_events_import"
    assert signal.title == "acme/api issue #42 labeled"
    assert signal.content == "labeled label bug"
    assert signal.author == "octocat"
    assert signal.metadata["repository"] == "acme/api"
    assert signal.metadata["issue_number"] == 42
    assert signal.metadata["event"] == "labeled"
    assert signal.metadata["actor"]["login"] == "octocat"
    assert signal.metadata["created_at"] == "2026-05-01T10:00:00Z"
    assert signal.metadata["raw"] == LABELED_EVENT
    assert "timeline-event" in signal.tags
    assert signals[1].url == "https://github.example/acme/api/issues/7"
    assert signals[1].content == "Related support escalation"


@pytest.mark.asyncio
async def test_github_issue_timeline_events_supports_owner_repo_and_page_limit() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.params["page"] == "1":
            return httpx.Response(200, json=[{**LABELED_EVENT, "id": 1}])
        return httpx.Response(200, json=[{**LABELED_EVENT, "id": 2}])

    adapter = GitHubIssueTimelineEventsAdapter(
        token="gh-token",
        owner="acme",
        repo="api",
        config={"issue_numbers": "42", "per_page": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert [request.url.params["page"] for request in requests] == ["1", "2"]
    assert [signal.metadata["github_issue_timeline_event_id"] for signal in signals] == [1, 2]


@pytest.mark.asyncio
async def test_github_issue_timeline_events_honors_limit_across_issue_numbers() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[{**LABELED_EVENT, "id": len(requests)}])

    adapter = GitHubIssueTimelineEventsAdapter(
        token="gh-token",
        config={"repository": "acme/api", "issue_numbers": [42, 43], "per_page": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert len(signals) == 1
    assert len(requests) == 1
    assert requests[0].url.path == "/repos/acme/api/issues/42/timeline"


@pytest.mark.asyncio
async def test_github_issue_timeline_events_missing_auth_config_or_errors_return_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    assert await GitHubIssueTimelineEventsAdapter(config={"repository": "acme/api", "issue_numbers": [42]}).fetch() == []
    assert await GitHubIssueTimelineEventsAdapter(token="token", config={"issue_numbers": [42]}).fetch() == []
    assert await GitHubIssueTimelineEventsAdapter(token="token", config={"repository": "acme/api"}).fetch() == []
    assert await GitHubIssueTimelineEventsAdapter(token="token", config={"repository": "acme/api", "issue_numbers": [42]}).fetch(limit=0) == []

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    adapter = GitHubIssueTimelineEventsAdapter(
        token="bad",
        config={"repository": "acme/api", "issue_numbers": [42]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    assert await adapter.fetch() == []
