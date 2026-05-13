"""Tests for Jira issue changelog import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.jira_issue_changelog_adapter import (
    JiraIssueChangelogAdapter,
    JiraIssueChangelogImportAdapter,
)
from max.types.signal import SignalSourceType


def _history(history_id: str, field: str = "status") -> dict:
    return {
        "id": history_id,
        "author": {
            "accountId": "acct-1",
            "displayName": "Rhea",
            "emailAddress": "rhea@example.com",
            "active": True,
        },
        "created": "2026-05-01T10:00:00.000+0000",
        "items": [
            {
                "field": field,
                "fieldtype": "jira",
                "fromString": "To Do",
                "toString": "In Progress",
            }
        ],
    }


@pytest.mark.asyncio
async def test_jira_issue_changelog_paginates_issue_keys_and_maps_signals() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/PROJ-1/changelog") and request.url.params["startAt"] == "0":
            return httpx.Response(200, json={"startAt": 0, "maxResults": 1, "total": 2, "values": [_history("1001")]})
        if request.url.path.endswith("/PROJ-1/changelog"):
            return httpx.Response(200, json={"startAt": 1, "maxResults": 1, "total": 2, "values": [_history("1002", "priority")]})
        return httpx.Response(200, json={"startAt": 0, "maxResults": 1, "total": 1, "values": [_history("2001", "assignee")]})

    adapter = JiraIssueChangelogImportAdapter(
        base_url="https://acme.atlassian.net",
        email="user@example.com",
        api_token="api-token",
        config={"issue_keys": ["PROJ-1", "PROJ-2"], "page_size": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=3)

    assert JiraIssueChangelogAdapter is JiraIssueChangelogImportAdapter
    assert len(requests) == 3
    assert requests[0].url.path == "/rest/api/3/issue/PROJ-1/changelog"
    assert requests[0].url.params["startAt"] == "0"
    assert requests[0].url.params["maxResults"] == "1"
    assert requests[1].url.params["startAt"] == "1"
    assert requests[2].url.path == "/rest/api/3/issue/PROJ-2/changelog"
    assert requests[0].headers["Authorization"].startswith("Basic ")
    assert [signal.id for signal in signals] == [
        "jira-issue-changelog:PROJ-1:1001",
        "jira-issue-changelog:PROJ-1:1002",
        "jira-issue-changelog:PROJ-2:2001",
    ]
    signal = signals[0]
    assert signal.source_type == SignalSourceType.ROADMAP
    assert signal.source_adapter == "jira_issue_changelog_import"
    assert signal.title == "PROJ-1 changelog updated status"
    assert "status: To Do -> In Progress" in signal.content
    assert signal.url == "https://acme.atlassian.net/browse/PROJ-1"
    assert signal.author == "Rhea"
    assert signal.published_at is not None
    assert signal.metadata["issue_key"] == "PROJ-1"
    assert signal.metadata["changelog_id"] == "1001"
    assert signal.metadata["changed_fields"] == ["status"]
    assert signal.metadata["author"]["account_id"] == "acct-1"
    assert "jira" in signal.tags
    assert "changelog" in signal.tags


@pytest.mark.asyncio
async def test_jira_issue_changelog_accepts_single_issue_key_and_respects_limit() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"startAt": 0, "maxResults": 2, "total": 2, "values": [_history("1"), _history("2")]})

    adapter = JiraIssueChangelogImportAdapter(
        base_url="https://acme.atlassian.net",
        email="user@example.com",
        token="api-token",
        config={"issue_key": "PROJ-1", "page_size": 50},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert len(requests) == 1
    assert requests[0].url.params["maxResults"] == "1"
    assert [signal.metadata["changelog_id"] for signal in signals] == ["1"]


@pytest.mark.asyncio
async def test_jira_issue_changelog_missing_config_env_and_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JIRA_BASE_URL", raising=False)
    monkeypatch.delenv("JIRA_EMAIL", raising=False)
    monkeypatch.delenv("JIRA_USERNAME", raising=False)
    monkeypatch.delenv("JIRA_API_TOKEN", raising=False)

    assert await JiraIssueChangelogImportAdapter(config={"issue_keys": ["PROJ-1"]}).fetch() == []
    assert await JiraIssueChangelogImportAdapter(base_url="https://acme.atlassian.net", email="user@example.com", api_token="token").fetch() == []
    assert await JiraIssueChangelogImportAdapter(base_url="https://acme.atlassian.net", email="user@example.com", api_token="token", config={"issue_key": "PROJ-1"}).fetch(limit=0) == []

    failing = JiraIssueChangelogImportAdapter(
        base_url="https://acme.atlassian.net",
        email="user@example.com",
        api_token="token",
        config={"issue_keys": ["PROJ-1"]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500))),
    )

    assert await failing.fetch(limit=2) == []
