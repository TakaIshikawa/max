"""Tests for Jira issue import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.jira_adapter import JiraAdapter


@pytest.mark.asyncio
async def test_jira_fetch_executes_jql_and_maps_cloud_payload() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "startAt": 0,
                "maxResults": 50,
                "total": 1,
                "issues": [
                    {
                        "id": "10001",
                        "key": "MAX-7",
                        "fields": {
                            "summary": "Import customer task",
                            "description": {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Readable Jira doc"}]}]},
                            "reporter": {"displayName": "Rhea", "emailAddress": "rhea@example.com"},
                            "assignee": {"displayName": "Ada", "emailAddress": "ada@example.com"},
                            "status": {"name": "In Progress"},
                            "priority": {"name": "High"},
                            "labels": ["customer"],
                            "components": [{"name": "Imports"}],
                            "created": "2026-05-01T12:00:00.000+0000",
                            "updated": "2026-05-02T12:00:00.000+0000",
                            "issuetype": {"name": "Task"},
                        },
                    }
                ],
            },
        )

    adapter = JiraAdapter(base_url="https://max.atlassian.net", email="user@example.com", token="token", config={"jql": "project = MAX"}, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    signals = await adapter.fetch(limit=5)

    assert requests[0].url.params["jql"] == "project = MAX"
    assert signals[0].title == "Import customer task"
    assert signals[0].content == "Readable Jira doc"
    assert signals[0].url == "https://max.atlassian.net/browse/MAX-7"
    assert signals[0].metadata["key"] == "MAX-7"
    assert signals[0].metadata["status"] == "In Progress"
    assert signals[0].metadata["priority"] == "High"
    assert signals[0].metadata["assignee"] == "Ada"
    assert signals[0].metadata["labels"] == ["customer"]
    assert signals[0].metadata["components"] == ["Imports"]
    assert signals[0].metadata["issue_type"] == "Task"


@pytest.mark.asyncio
async def test_jira_fetch_paginates_until_limit() -> None:
    starts: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        starts.append(request.url.params["startAt"])
        if request.url.params["startAt"] == "0":
            return httpx.Response(200, json={"startAt": 0, "maxResults": 1, "total": 2, "issues": [{"id": "1", "key": "MAX-1", "fields": {"summary": "One"}}]})
        return httpx.Response(200, json={"startAt": 1, "maxResults": 1, "total": 2, "issues": [{"id": "2", "key": "MAX-2", "fields": {"summary": "Two"}}]})

    adapter = JiraAdapter(base_url="https://jira.test", token="token", config={"max_results": 1}, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    signals = await adapter.fetch(limit=2)

    assert [signal.metadata["key"] for signal in signals] == ["MAX-1", "MAX-2"]
    assert starts == ["0", "1"]


@pytest.mark.asyncio
async def test_jira_http_error_returns_empty() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401)

    adapter = JiraAdapter(base_url="https://jira.test", token="bad", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert await adapter.fetch() == []
