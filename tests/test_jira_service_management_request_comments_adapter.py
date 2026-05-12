"""Tests for Jira Service Management request comments import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.jira_service_management_request_comments_adapter import JiraServiceManagementRequestCommentsAdapter
from max.types.signal import SignalSourceType


COMMENT = {
    "id": "10020",
    "body": "We can reproduce this on the export job.",
    "public": True,
    "author": {
        "accountId": "acct-1",
        "displayName": "Rhea",
        "emailAddress": "rhea@example.com",
    },
    "created": {"iso8601": "2026-05-01T10:00:00+0000"},
    "_links": {"self": "https://acme.atlassian.net/rest/servicedeskapi/request/HELP-77/comment/10020"},
}


@pytest.mark.asyncio
async def test_jsm_request_comments_fetches_cloud_pages_and_maps() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json={"start": 0, "limit": 1, "isLastPage": False, "values": [COMMENT]})
        return httpx.Response(200, json={"start": 1, "limit": 1, "isLastPage": True, "values": [{**COMMENT, "id": "10021", "public": False}]})

    adapter = JiraServiceManagementRequestCommentsAdapter(
        cloud_id="cloud-1",
        bearer_token="jsm-token",
        config={"request_keys": ["HELP-77"], "page_size": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert len(requests) == 2
    assert requests[0].url.path == "/ex/jira/cloud-1/rest/servicedeskapi/request/HELP-77/comment"
    assert requests[0].url.params["start"] == "0"
    assert requests[0].url.params["limit"] == "1"
    assert requests[1].url.params["start"] == "1"
    assert requests[0].headers["Authorization"] == "Bearer jsm-token"
    assert signals[0].id == "jira-service-management-request-comment:HELP-77:10020"
    assert signals[0].source_type == SignalSourceType.ROADMAP
    assert signals[0].source_adapter == "jira_service_management_request_comments_import"
    assert signals[0].title == "HELP-77 request comment"
    assert signals[0].content == "We can reproduce this on the export job."
    assert signals[0].author == "Rhea"
    assert signals[0].metadata["request_identifier"] == "HELP-77"
    assert signals[0].metadata["request_key"] == "HELP-77"
    assert signals[0].metadata["comment_id"] == "10020"
    assert signals[0].metadata["visibility"] == "public"
    assert signals[0].metadata["public"] is True
    assert signals[0].metadata["author"]["email"] == "rhea@example.com"
    assert signals[0].metadata["body"] == "We can reproduce this on the export job."
    assert signals[0].metadata["created_at"] == "2026-05-01T10:00:00+0000"
    assert signals[0].metadata["source_url"] == "https://acme.atlassian.net/rest/servicedeskapi/request/HELP-77/comment/10020"
    assert signals[1].metadata["visibility"] == "internal"


@pytest.mark.asyncio
async def test_jsm_request_comments_empty_and_multiple_requests() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if "HELP-77" in request.url.path:
            return httpx.Response(200, json={"isLastPage": True, "values": []})
        return httpx.Response(200, json={"isLastPage": True, "values": [{**COMMENT, "id": "10022"}]})

    adapter = JiraServiceManagementRequestCommentsAdapter(
        site_url="https://acme.atlassian.net",
        email="user@example.com",
        token="api-token",
        config={"request_keys": ["HELP-77", "HELP-78"]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert len(requests) == 2
    assert requests[0].url.path == "/rest/servicedeskapi/request/HELP-77/comment"
    assert requests[1].url.path == "/rest/servicedeskapi/request/HELP-78/comment"
    assert requests[0].headers["Authorization"].startswith("Basic ")
    assert len(signals) == 1
    assert signals[0].metadata["request_identifier"] == "HELP-78"


@pytest.mark.asyncio
async def test_jsm_request_comments_missing_optional_fields_and_missing_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JIRA_SERVICE_MANAGEMENT_TOKEN", raising=False)
    assert await JiraServiceManagementRequestCommentsAdapter(cloud_id="cloud-1", config={"request_key": "HELP-77"}).fetch() == []
    assert await JiraServiceManagementRequestCommentsAdapter(cloud_id="cloud-1", bearer_token="token").fetch() == []
    assert await JiraServiceManagementRequestCommentsAdapter(cloud_id="cloud-1", bearer_token="token", config={"request_key": "HELP-77"}).fetch(limit=0) == []

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"isLastPage": True, "values": [{"id": "10023", "body": {"value": ""}}]})

    adapter = JiraServiceManagementRequestCommentsAdapter(
        site_url="https://acme.atlassian.net",
        bearer_token="jsm-token",
        config={"request_id": "77"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert signals[0].author is None
    assert signals[0].content == ""
    assert signals[0].metadata["request_id"] == "77"
    assert signals[0].metadata["request_key"] is None
    assert signals[0].metadata["visibility"] == ""
    assert signals[0].metadata["source_url"] == "https://acme.atlassian.net/browse/77"
