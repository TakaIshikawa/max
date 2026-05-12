"""Tests for Jira issue comments import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.jira_issue_comments_adapter import (
    JiraIssueCommentsAdapter,
    JiraIssueCommentsImportAdapter,
)
from max.types.signal import SignalSourceType


def _comment(number: int, *, rendered: bool = False) -> dict:
    comment = {
        "id": str(1000 + number),
        "self": f"https://acme.atlassian.net/rest/api/3/issue/PROJ-1/comment/{1000 + number}",
        "author": {
            "accountId": "acct-1",
            "displayName": "Rhea",
            "emailAddress": "rhea@example.com",
            "active": True,
        },
        "body": {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": f"Plain body {number}"}],
                }
            ],
        },
        "created": "2026-05-01T10:00:00.000+0000",
        "updated": f"2026-05-0{number}T11:00:00.000+0000",
        "visibility": {"type": "role", "value": "Developers"},
    }
    if rendered:
        comment["renderedBody"] = f"<p>Rendered body {number}</p>"
    return comment


@pytest.mark.asyncio
async def test_jira_issue_comments_paginates_multiple_issues_and_maps_signals() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/PROJ-1/comment") and request.url.params["startAt"] == "0":
            return httpx.Response(200, json={"startAt": 0, "maxResults": 1, "total": 2, "comments": [_comment(1, rendered=True)]})
        if request.url.path.endswith("/PROJ-1/comment"):
            return httpx.Response(200, json={"startAt": 1, "maxResults": 1, "total": 2, "comments": [_comment(2)]})
        return httpx.Response(200, json={"startAt": 0, "maxResults": 1, "total": 1, "comments": [_comment(3)]})

    adapter = JiraIssueCommentsImportAdapter(
        base_url="https://acme.atlassian.net",
        email="user@example.com",
        token="api-token",
        config={"issue_keys": ["PROJ-1", "PROJ-2"], "expand": ["renderedBody"], "per_page": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=3)

    assert JiraIssueCommentsAdapter is JiraIssueCommentsImportAdapter
    assert len(requests) == 3
    assert requests[0].url.path == "/rest/api/3/issue/PROJ-1/comment"
    assert requests[0].url.params["startAt"] == "0"
    assert requests[0].url.params["maxResults"] == "1"
    assert requests[0].url.params["expand"] == "renderedBody"
    assert requests[1].url.params["startAt"] == "1"
    assert requests[2].url.path == "/rest/api/3/issue/PROJ-2/comment"
    assert requests[0].headers["Authorization"].startswith("Basic ")
    assert len(signals) == 3
    assert signals[0].id == "jira-issue-comment:PROJ-1:1001"
    assert signals[0].source_type == SignalSourceType.ROADMAP
    assert signals[0].source_adapter == "jira_issue_comments_import"
    assert signals[0].title == "PROJ-1 issue comment"
    assert signals[0].content == "<p>Rendered body 1</p>"
    assert signals[0].url == "https://acme.atlassian.net/rest/api/3/issue/PROJ-1/comment/1001"
    assert signals[0].author == "Rhea"
    assert signals[0].published_at is not None
    assert signals[0].metadata["issue_key"] == "PROJ-1"
    assert signals[0].metadata["comment_id"] == "1001"
    assert signals[0].metadata["author"]["account_id"] == "acct-1"
    assert signals[0].metadata["updated_at"] == "2026-05-01T11:00:00.000+0000"
    assert signals[0].metadata["rendered_body"] == "<p>Rendered body 1</p>"
    assert signals[0].metadata["body"] == "<p>Rendered body 1</p>"
    assert signals[0].metadata["visibility"] == "role"
    assert signals[0].metadata["self_url"] == "https://acme.atlassian.net/rest/api/3/issue/PROJ-1/comment/1001"
    assert signals[1].metadata["body"] == "Plain body 2"
    assert signals[2].metadata["issue_key"] == "PROJ-2"


@pytest.mark.asyncio
async def test_jira_issue_comments_respects_limit_before_next_issue() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"startAt": 0, "maxResults": 2, "total": 2, "comments": [_comment(1), _comment(2)]})

    adapter = JiraIssueCommentsImportAdapter(
        base_url="https://acme.atlassian.net",
        email="user@example.com",
        token="api-token",
        config={"issue_keys": ["PROJ-1", "PROJ-2"], "per_page": 100},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert len(requests) == 1
    assert requests[0].url.params["maxResults"] == "1"
    assert [signal.metadata["comment_id"] for signal in signals] == ["1001"]


@pytest.mark.asyncio
async def test_jira_issue_comments_missing_config_env_and_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JIRA_BASE_URL", raising=False)
    monkeypatch.delenv("JIRA_EMAIL", raising=False)
    monkeypatch.delenv("JIRA_USERNAME", raising=False)
    monkeypatch.delenv("JIRA_API_TOKEN", raising=False)

    assert await JiraIssueCommentsImportAdapter(config={"issue_keys": ["PROJ-1"]}).fetch() == []
    assert await JiraIssueCommentsImportAdapter(base_url="https://acme.atlassian.net", email="user@example.com", token="token").fetch() == []
    assert await JiraIssueCommentsImportAdapter(base_url="https://acme.atlassian.net", email="user@example.com", token="token", config={"issue_key": "PROJ-1"}).fetch(limit=0) == []

    failing = JiraIssueCommentsImportAdapter(
        base_url="https://acme.atlassian.net",
        email="user@example.com",
        token="token",
        config={"issue_keys": ["PROJ-1"]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500))),
    )

    assert await failing.fetch(limit=2) == []
